"""EBA (Eğitim Bilişim Ağı) karekod ile giriş / hesap bağlama view'ları.

İki bağımsız akış paylaşır (bkz. models.EbaOturum):
  - "Giriş": giriş sayfasından, kimliği doğrulanmamış bir ziyaretçi tarafından
    başlatılır. EBA doğrulaması geldiğinde `EbaHesap` üzerinden bağlı bir
    Personel/User bulunursa doğrudan giriş yapılır (bkz. `eba_giris_durum`).
  - "Hesap Bağlama": kimliği doğrulanmış bir kullanıcı, kendi profilinden,
    kendi Personel kaydına bir EBA kimliği bağlamak için başlatır (bkz.
    `eba_baglama_durum`). Bu adım olmadan hiçbir EBA kimliği bir hesaba
    giriş yaptıramaz — proje kararı: "yalnızca var olan hesaba bağlama",
    lightdm projesindeki gibi otomatik hesap oluşturma YOK.

Websocket bağlantısını bu senkron view'lar değil, ayrı süreç olarak çalışan
`eba_ws_worker` yönetim komutu yönetir (bkz. o modülün ve
`services/eba_client.py`'nin docstring'i); view'lar yalnızca `EbaOturum`
satırını oluşturur/okur.

Güvenlik notları (bkz. models.EbaOturum.baslatan_session_key docstring'i):
  - `token` (128 bit rastgele) tek başına giriş yapmaya YETMEZ — `eba_giris_durum`
    yalnızca oturumu BAŞLATAN tarayıcı oturumundan gelen bir yoklamayla girişi
    tamamlar. Bu olmadan, token'ı herhangi bir yolla (sunucu erişim logları,
    tarayıcı geçmişi, paylaşılan ekran) görmüş biri, `durum=dogrulandi` anındaki
    dar pencerede KENDİ tarayıcısından bir istekle öğretmenin hesabına giriş
    yapabilirdi.
  - `eba_giris_baslat`/`eba_baglama_baslat`, EBA'nın gerçek sunucusuna karşı
    (worker üzerinden) yeni bir websocket bağlantısı açar — anonim ve ücretsiz
    bir eylem olduğundan IP başına kaba bir istek sınırı uygulanır (bkz.
    `_rate_limit_asildi_mi`); aksi hâlde bir saldırgan hem bizim işçimizi hem de
    EBA'nın sunucusunu (bizim IP'imiz üzerinden) aşırı isteğe boğabilirdi.
  - Doğrulanan `eba_id`/`eba_adi_soyadi`, akış tamamlanır tamamlanmaz `EbaOturum`
    satırından temizlenir (veri asgarileştirme) — kalıcı kayıt zaten `EbaHesap`'ta
    tutulur; `EbaOturum` yalnızca akışın kendisi için geçici bir durum tablosudur.
"""
import base64
import io

import qrcode
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import EbaHesap, EbaOturum

RATE_LIMIT_PENCERE_SN = 60
RATE_LIMIT_MAKS_ISTEK = 20


def _istemci_ip(request):
    """İstemci IP'sini döner. `X-Real-IP`, yalnızca kendi nginx yapılandırmamız
    tarafından (bkz. kurulumcu/sunucu.py: nginx_yapilandir) tek atlamalı olarak
    ayarlanır — gunicorn yalnızca nginx'in bağlandığı bir unix soketi dinlediği
    için istemciden doğrudan sahte bir değer gelemez; bu yüzden burada güvenle
    öncelikli kabul edilir. Ne o ne REMOTE_ADDR varsa (ör. yerel `runserver`
    testinde soket bilgisi eksikse) None döner — rate limit bu durumda atlanır."""
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR")


def _rate_limit_asildi_mi(ip, amac):
    """IP başına, `amac` bazında kaba bir istek sınırı uygular (bkz. modül
    docstring'i). Gerçek IP alınamıyorsa (None) engellemeden geçer — bir
    saldırganın IP'yi göndermemesi (zaten kontrolünde olmayan bir başlık)
    engellemeyi atlatmasına yol açmaz, yalnızca teşhis edilemeyen ortamlarda
    (ör. bazı yerel geliştirme kurulumları) özelliği kilitlemez."""
    if not ip:
        return False
    sinir = timezone.now() - timezone.timedelta(seconds=RATE_LIMIT_PENCERE_SN)
    sayi = EbaOturum.objects.filter(
        amac=amac, istek_ip=ip, olusturma_zamani__gte=sinir
    ).count()
    return sayi >= RATE_LIMIT_MAKS_ISTEK


def _rate_limit_yaniti():
    return JsonResponse(
        {"hata": "Çok fazla deneme yapıldı. Lütfen bir dakika sonra tekrar deneyin."},
        status=429,
    )


def _qr_png_base64(veri):
    img = qrcode.make(veri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _suresi_gecmisse_guncelle(oturum):
    if oturum.durum == EbaOturum.DURUM_QR_HAZIR and oturum.suresi_doldu_mu():
        oturum.durum = EbaOturum.DURUM_SURESI_DOLDU
        oturum.mesaj = "QR süresi doldu, sayfayı yenileyip tekrar deneyin."
        oturum.save(update_fields=["durum", "mesaj"])


def _temel_yanit(oturum):
    yanit = {"durum": oturum.durum, "mesaj": oturum.mesaj}
    if oturum.durum == EbaOturum.DURUM_QR_HAZIR and oturum.qr_uuid:
        yanit["qr_png_base64"] = _qr_png_base64(oturum.qr_uuid)
    return yanit


# ─────────────────────────────────────────────
# Giriş akışı (anonim erişilebilir — bu, girişin kendisi)
# ─────────────────────────────────────────────


@require_POST
def eba_giris_baslat(request):
    ip = _istemci_ip(request)
    if _rate_limit_asildi_mi(ip, EbaOturum.AMAC_GIRIS):
        return _rate_limit_yaniti()

    # Bu akışı başlatan tarayıcı oturumunu sabitlemek için bir Django oturumu
    # (ve dolayısıyla bir `sessionid` çerezi) zorlanır — bkz. models.EbaOturum.
    # baslatan_session_key docstring'i. Kimlik doğrulanmamış bir ziyaretçide
    # normalde hiçbir şey oturuma yazılmadığı sürece çerez oluşmaz.
    if not request.session.session_key:
        request.session["eba_giris_baslatildi"] = True
        request.session.save()

    oturum = EbaOturum.objects.create(
        amac=EbaOturum.AMAC_GIRIS,
        baslatan_session_key=request.session.session_key,
        istek_ip=ip,
    )
    return JsonResponse({"token": oturum.token})


def eba_giris_durum(request, token):
    oturum = get_object_or_404(EbaOturum, token=token, amac=EbaOturum.AMAC_GIRIS)
    _suresi_gecmisse_guncelle(oturum)

    # Bu isteğin, oturumu BAŞLATAN tarayıcıdan geldiğini doğrula (bkz. modül
    # docstring'i). Eşleşmiyorsa — token bir şekilde başka biri tarafından ele
    # geçirilmiş olabilir — hiçbir zaman giriş TAMAMLANMAZ; gerçek sahibi
    # olmadığını belli etmeden, sanki henüz doğrulanmamış gibi bir yanıt döner.
    # Gerçek sahip (doğru oturum anahtarına sahip tarayıcı) bir sonraki
    # yoklamasında girişi normal şekilde tamamlayabilir.
    sahibi_mi = (
        not oturum.baslatan_session_key
        or oturum.baslatan_session_key == request.session.session_key
    )
    if not sahibi_mi:
        if oturum.durum == EbaOturum.DURUM_DOGRULANDI:
            return JsonResponse({"durum": EbaOturum.DURUM_QR_HAZIR, "mesaj": ""})
        return JsonResponse(_temel_yanit(oturum))

    yanit = _temel_yanit(oturum)

    if oturum.durum == EbaOturum.DURUM_DOGRULANDI:
        personel = oturum.eslesen_personel
        if personel and personel.user_id:
            personel.user.backend = "django.contrib.auth.backends.ModelBackend"
            login(request, personel.user)
            oturum.durum = EbaOturum.DURUM_TAMAMLANDI
            oturum.eba_id = ""
            oturum.eba_adi_soyadi = ""
            oturum.save(update_fields=["durum", "eba_id", "eba_adi_soyadi"])

            hedef = request.GET.get("next", "")
            if not (hedef and url_has_allowed_host_and_scheme(
                hedef, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            )):
                hedef = "/"
            yanit = {"durum": EbaOturum.DURUM_TAMAMLANDI, "mesaj": "", "redirect": hedef}
        else:
            oturum.durum = EbaOturum.DURUM_HATA
            oturum.mesaj = "Bu personele bağlı bir kullanıcı hesabı yok."
            oturum.save(update_fields=["durum", "mesaj"])
            yanit = {"durum": oturum.durum, "mesaj": oturum.mesaj}

    return JsonResponse(yanit)


# ─────────────────────────────────────────────
# Hesap bağlama akışı (yalnızca giriş yapmış kullanıcı kendi hesabına)
# ─────────────────────────────────────────────


@login_required
@require_POST
def eba_baglama_baslat(request):
    personel = getattr(request.user, "personel", None)
    if personel is None:
        return JsonResponse(
            {"hata": "Bu kullanıcıya bağlı bir personel kaydı bulunmuyor."}, status=400
        )

    ip = _istemci_ip(request)
    if _rate_limit_asildi_mi(ip, EbaOturum.AMAC_BAGLAMA):
        return _rate_limit_yaniti()

    # Bağlama akışında güvenlik `request.user` ile zaten sağlanıyor (bkz.
    # eba_baglama_durum'daki baglanacak_personel__user=request.user filtresi) —
    # oturum anahtarı burada yalnızca tutarlılık/denetim amaçlıdır.
    oturum = EbaOturum.objects.create(
        amac=EbaOturum.AMAC_BAGLAMA,
        baglanacak_personel=personel,
        baslatan_session_key=request.session.session_key or "",
        istek_ip=ip,
    )
    return JsonResponse({"token": oturum.token})


@login_required
def eba_baglama_durum(request, token):
    oturum = get_object_or_404(
        EbaOturum,
        token=token,
        amac=EbaOturum.AMAC_BAGLAMA,
        baglanacak_personel__user=request.user,
    )
    _suresi_gecmisse_guncelle(oturum)
    yanit = _temel_yanit(oturum)

    if oturum.durum == EbaOturum.DURUM_DOGRULANDI:
        celisen = (
            EbaHesap.objects.filter(eba_id=oturum.eba_id)
            .exclude(personel=oturum.baglanacak_personel)
            .select_related("personel")
            .first()
        )
        if celisen:
            oturum.durum = EbaOturum.DURUM_HATA
            oturum.mesaj = f"Bu EBA hesabı zaten '{celisen.personel}' personeline bağlı."
        else:
            EbaHesap.objects.update_or_create(
                personel=oturum.baglanacak_personel,
                defaults={"eba_id": oturum.eba_id, "eba_adi_soyadi": oturum.eba_adi_soyadi},
            )
            oturum.durum = EbaOturum.DURUM_TAMAMLANDI
            oturum.mesaj = "EBA hesabınız başarıyla bağlandı."
        oturum.eba_id = ""
        oturum.eba_adi_soyadi = ""
        oturum.save(update_fields=["durum", "mesaj", "eba_id", "eba_adi_soyadi"])
        yanit = {"durum": oturum.durum, "mesaj": oturum.mesaj}

    return JsonResponse(yanit)


@login_required
@require_POST
def eba_baglama_kaldir(request):
    personel = getattr(request.user, "personel", None)
    if personel is not None:
        EbaHesap.objects.filter(personel=personel).delete()
        messages.success(request, "EBA hesabı bağlantısı kaldırıldı.")
    return redirect("profil")
