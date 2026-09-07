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
"""
import base64
import io

import qrcode
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import EbaHesap, EbaOturum


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
    oturum = EbaOturum.objects.create(amac=EbaOturum.AMAC_GIRIS)
    return JsonResponse({"token": oturum.token})


def eba_giris_durum(request, token):
    oturum = get_object_or_404(EbaOturum, token=token, amac=EbaOturum.AMAC_GIRIS)
    _suresi_gecmisse_guncelle(oturum)
    yanit = _temel_yanit(oturum)

    if oturum.durum == EbaOturum.DURUM_DOGRULANDI:
        personel = oturum.eslesen_personel
        if personel and personel.user_id:
            personel.user.backend = "django.contrib.auth.backends.ModelBackend"
            login(request, personel.user)
            oturum.durum = EbaOturum.DURUM_TAMAMLANDI
            oturum.save(update_fields=["durum"])

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
    oturum = EbaOturum.objects.create(amac=EbaOturum.AMAC_BAGLAMA, baglanacak_personel=personel)
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
        oturum.save(update_fields=["durum", "mesaj"])
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
