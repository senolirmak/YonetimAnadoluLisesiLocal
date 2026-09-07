"""EBA QR websocket istemcisi — tek bir EbaOturum'u baştan sona yürütür.

Kaynak: `home/senolirmak/Projeler/lightdm/` (ebaqr-greeter paketi,
`modules/ebaws.py` + `usr/bin/ebaqr-greeter-service`, GPL-3.0+, Pardus
<dev@pardus.org.tr>, https://github.com/pardus). O projede tek bir root
servisi tüm makine için SÜREKLİ açık bir websocket tutar (bağlantı kimliği:
fiziksel makinenin MAC adresi). Burada, çok kullanıcılı bir web girişi için,
her `EbaOturum` kendi KISA ÖMÜRLÜ bağlantısını açar ve URL'deki kimlik MAC
yerine oturumun rastgele `token`'ıdır — gerçek EBA sunucusunun bunu kabul
edip etmeyeceği doğrulanmadı, bkz. `EBA_QR_WS_URL` ayarı ve proje kararı
("önce mock sunucuyla prototip"). Mesaj protokolü (register → {uuid,
expire_at} → QR → {type: validation, user_data}) upstream'le birebir aynı.

`calistir(oturum_id)`, `eba_ws_worker` yönetim komutu tarafından her bekleyen
oturum için ayrı bir asyncio görevi olarak başlatılır (bkz. o modülün
docstring'i).
"""
import asyncio
import json
from datetime import datetime
from datetime import timezone as dt_timezone

import websockets
from asgiref.sync import sync_to_async
from django.conf import settings

from ..models import EbaHesap, EbaOturum

# Register'dan sonra bir QR'ın taranmasını bekleme üst sınırı. EBA'nın kendi
# `expire_at`'i genelde bundan daha kısa olur (bkz. handle_ws_event) — bu,
# EBA hiç `expire_at` göndermezse ya da bağlantı sessizce asılı kalırsa
# devreye giren bağımsız bir güvenlik ağıdır.
VARSAYILAN_ZAMAN_ASIMI = 90


@sync_to_async
def _durumu_guncelle(oturum_id, **alanlar):
    EbaOturum.objects.filter(pk=oturum_id).update(**alanlar)


@sync_to_async
def _oturum_amaci_ve_token(oturum_id):
    try:
        return EbaOturum.objects.values_list("amac", "token").get(pk=oturum_id)
    except EbaOturum.DoesNotExist:
        return None, None


@sync_to_async
def _eslesen_personeli_bul(eba_id):
    hesap = EbaHesap.objects.select_related("personel").filter(eba_id=eba_id).first()
    return hesap.personel if hesap else None


def _epoch_to_dt(deger):
    """EBA'nın gönderdiği unix-epoch `expire_at`'i aware datetime'a çevirir."""
    return datetime.fromtimestamp(int(deger), tz=dt_timezone.utc)


async def _mesaji_isle(oturum_id, amac, veri):
    """Gelen tek bir websocket mesajını işler. Akış bittiyse (doğrulandı/hata)
    True, devam edilecekse (yalnızca QR/durum güncellemesi) False döner."""
    if veri.get("type") == "validation" and "user_data" in veri:
        kullanici_verisi = veri["user_data"]
        eba_id = str(kullanici_verisi.get("uid", "")).strip()
        ad_soyad = str(kullanici_verisi.get("uname", "")).strip()
        if not eba_id:
            await _durumu_guncelle(
                oturum_id, durum=EbaOturum.DURUM_HATA, mesaj="EBA doğrulama verisi eksik."
            )
            return True

        if amac == EbaOturum.AMAC_BAGLAMA:
            # Hesap bağlama akışında EbaHesap kaydı burada değil, view'da
            # (eba_baglama_durum) oluşturulur/güncellenir — request.user zaten
            # biliniyor ve senkron bir view'da ORM'e daha doğal erişilir;
            # worker yalnızca EBA'nın doğruladığı kimliği yazar.
            await _durumu_guncelle(
                oturum_id,
                durum=EbaOturum.DURUM_DOGRULANDI,
                eba_id=eba_id,
                eba_adi_soyadi=ad_soyad,
            )
            return True

        # Giriş akışı: bu eba_id'nin önceden bağlandığı bir Personel var mı?
        personel = await _eslesen_personeli_bul(eba_id)
        if personel is None:
            await _durumu_guncelle(
                oturum_id,
                durum=EbaOturum.DURUM_HATA,
                eba_id=eba_id,
                eba_adi_soyadi=ad_soyad,
                mesaj=(
                    "Bu EBA hesabı sisteme bağlı değil. Önce kullanıcı adı/şifrenizle "
                    "giriş yapıp profilinizden EBA hesabınızı bağlayın."
                ),
            )
            return True
        if personel.user_id is None:
            await _durumu_guncelle(
                oturum_id,
                durum=EbaOturum.DURUM_HATA,
                mesaj="Bu personele bağlı bir kullanıcı hesabı yok.",
            )
            return True

        await _durumu_guncelle(
            oturum_id,
            durum=EbaOturum.DURUM_DOGRULANDI,
            eba_id=eba_id,
            eba_adi_soyadi=ad_soyad,
            eslesen_personel_id=personel.pk,
        )
        return True

    # Doğrulama değilse QR/durum bilgisi güncellemesidir (uuid/expire_at/message).
    guncellenecek = {}
    if "uuid" in veri:
        guncellenecek["qr_uuid"] = veri["uuid"]
        guncellenecek["durum"] = EbaOturum.DURUM_QR_HAZIR
    if "expire_at" in veri:
        try:
            guncellenecek["qr_expire_at"] = _epoch_to_dt(veri["expire_at"])
        except (TypeError, ValueError):
            pass
    if veri.get("message"):
        guncellenecek["mesaj"] = veri["message"]
    if veri.get("action") in ("timeout", "failed"):
        await _durumu_guncelle(
            oturum_id,
            durum=EbaOturum.DURUM_SURESI_DOLDU,
            mesaj="QR süresi doldu, sayfayı yenileyip tekrar deneyin.",
        )
        return True
    if guncellenecek:
        await _durumu_guncelle(oturum_id, **guncellenecek)
    return False


async def calistir(oturum_id, zaman_asimi=VARSAYILAN_ZAMAN_ASIMI):
    """`oturum_id`'ye ait EbaOturum için websocket akışını baştan sona yürütür.

    Her oturum kendi bağlantısını açıp kapatır (bkz. modül docstring'i);
    `eba_ws_worker` bu fonksiyonu bekleyen her oturum için ayrı bir asyncio
    görevi olarak çalıştırır."""
    amac, token = await _oturum_amaci_ve_token(oturum_id)
    if amac is None:
        return

    ws_url = settings.EBA_QR_WS_URL.format(token=token)

    try:
        async with websockets.connect(ws_url, open_timeout=10) as ws:
            await ws.send(json.dumps({"action": "register"}))
            son_an = asyncio.get_event_loop().time() + zaman_asimi
            while True:
                kalan = son_an - asyncio.get_event_loop().time()
                if kalan <= 0:
                    await _durumu_guncelle(
                        oturum_id,
                        durum=EbaOturum.DURUM_SURESI_DOLDU,
                        mesaj="QR süresi doldu, sayfayı yenileyip tekrar deneyin.",
                    )
                    return
                try:
                    ham = await asyncio.wait_for(ws.recv(), timeout=kalan)
                except asyncio.TimeoutError:
                    continue
                veri = json.loads(ham)
                if await _mesaji_isle(oturum_id, amac, veri):
                    return
    except (websockets.exceptions.WebSocketException, OSError, asyncio.TimeoutError):
        await _durumu_guncelle(
            oturum_id,
            durum=EbaOturum.DURUM_HATA,
            mesaj="EBA QR servisine bağlanılamadı.",
        )
