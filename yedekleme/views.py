"""Yedekleme app view'ları.

Tümü yalnızca müdür yardımcısına açıktır (mudur_yardimcisi_required) — geri
yükleme canlı veritabanının tamamını değiştirebilen, geri alınamaz bir işlem
olduğu için README'deki rol tablosundaki en yüksek yetkiyle sınırlandırılmıştır.
Aynı gerekçeyle `yedek_yukle` de bu yetkiyle sınırlıdır: dışarıdan yüklenen bir
dosya da (bir sonraki adımda) geri yükleme akışına girebilir.
"""

from __future__ import annotations

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from okul.auth import mudur_yardimcisi_required
from yedekleme.forms import GeriYuklemeOnayForm, YedekYuklemeForm
from yedekleme.services import gdrive_servisi, yedek_servisi


def _guvenli_yol_veya_404(dosya_adi: str):
    try:
        return yedek_servisi.guvenli_yol(dosya_adi)
    except yedek_servisi.YedekHatasi:
        raise Http404 from None


@mudur_yardimcisi_required
def yedek_listesi(request):
    yedekler = yedek_servisi.yedekleri_listele()
    return render(
        request,
        "yedekleme/yedek_listesi.html",
        {"yedekler": yedekler, "gdrive_aktif": gdrive_servisi.aktif_mi()},
    )


@mudur_yardimcisi_required
@require_POST
def yedek_olustur(request):
    try:
        yol = yedek_servisi.yedek_olustur(etiket="web")
    except yedek_servisi.YedekHatasi as exc:
        messages.error(request, str(exc))
        return redirect("yedekleme:yedek_listesi")

    messages.success(request, f"Yedek oluşturuldu: {yol.name}")

    # Google Drive yapılandırılmışsa (bkz. gdrive_servisi) her yeni yedeği
    # otomatik olarak da oraya yükle — site-dışı bir kopya, felaket kurtarma
    # amaçlı. Yükleme başarısız olsa bile yerel yedek zaten alınmış olduğu
    # için bu işlemi geri almıyoruz, sadece uyarı gösteriyoruz.
    if gdrive_servisi.aktif_mi():
        try:
            gdrive_servisi.yedek_yukle(yol)
        except yedek_servisi.YedekHatasi as exc:
            messages.warning(request, f"Yedek Google Drive'a yüklenemedi: {exc}")
        else:
            messages.success(request, "Google Drive'a da yüklendi.")

    return redirect("yedekleme:yedek_listesi")


@mudur_yardimcisi_required
@require_POST
def yedek_drive_yukle(request, dosya_adi):
    yol = _guvenli_yol_veya_404(dosya_adi)
    try:
        gdrive_servisi.yedek_yukle(yol)
    except yedek_servisi.YedekHatasi as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"'{dosya_adi}' Google Drive'a yüklendi.")
    return redirect("yedekleme:yedek_listesi")


@mudur_yardimcisi_required
@require_POST
def yedek_yukle(request):
    form = YedekYuklemeForm(request.POST, request.FILES)
    if not form.is_valid():
        for hatalar in form.errors.values():
            for hata in hatalar:
                messages.error(request, hata)
        return redirect("yedekleme:yedek_listesi")

    try:
        yol = yedek_servisi.yedek_yukle(form.cleaned_data["dosya"])
    except yedek_servisi.YedekHatasi as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Yedek yüklendi: {yol.name}")
    return redirect("yedekleme:yedek_listesi")


@mudur_yardimcisi_required
def yedek_indir(request, dosya_adi):
    yol = _guvenli_yol_veya_404(dosya_adi)
    return FileResponse(open(yol, "rb"), as_attachment=True, filename=yol.name)


@mudur_yardimcisi_required
def yedek_sil_onay(request, dosya_adi):
    yol = _guvenli_yol_veya_404(dosya_adi)
    return render(request, "yedekleme/sil_onay.html", {"yedek": yol})


@mudur_yardimcisi_required
@require_POST
def yedek_sil(request, dosya_adi):
    try:
        yedek_servisi.yedek_sil(dosya_adi)
    except yedek_servisi.YedekHatasi as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"'{dosya_adi}' silindi.")
    return redirect("yedekleme:yedek_listesi")


@mudur_yardimcisi_required
def yedek_geri_yukle_onay(request, dosya_adi):
    yol = _guvenli_yol_veya_404(dosya_adi)
    form = GeriYuklemeOnayForm(initial={"dosya_adi": dosya_adi})

    try:
        rapor = yedek_servisi.yedek_raporu(yol)
    except yedek_servisi.YedekHatasi as exc:
        rapor = None
        messages.warning(request, f"Yedek raporu oluşturulamadı, yine de geri yükleyebilirsiniz: {exc}")

    return render(
        request, "yedekleme/geri_yukle_onay.html", {"yedek": yol, "form": form, "rapor": rapor}
    )


@mudur_yardimcisi_required
@require_POST
def yedek_geri_yukle(request):
    form = GeriYuklemeOnayForm(request.POST)
    dosya_adi = request.POST.get("dosya_adi", "")

    if not form.is_valid():
        for hatalar in form.errors.values():
            for hata in hatalar:
                messages.error(request, hata)
        return redirect("yedekleme:yedek_geri_yukle_onay", dosya_adi=dosya_adi)

    dosya_adi = form.cleaned_data["dosya_adi"]

    # Geri yüklemeden hemen önce otomatik bir güvenlik yedeği al — bu başarısız
    # olursa geri yükleme hiç başlatılmaz.
    try:
        guvenlik_yedegi = yedek_servisi.yedek_olustur(etiket="restore_oncesi")
    except yedek_servisi.YedekHatasi as exc:
        messages.error(request, f"Güvenlik yedeği alınamadığı için geri yükleme iptal edildi: {exc}")
        return redirect("yedekleme:yedek_listesi")

    try:
        yedek_servisi.yedek_geri_yukle(dosya_adi)
    except yedek_servisi.YedekHatasi as exc:
        messages.error(
            request,
            f"Geri yükleme sırasında hata oluştu: {exc} "
            f"(işlem öncesi güvenlik yedeği: {guvenlik_yedegi.name})",
        )
    else:
        messages.success(
            request,
            f"'{dosya_adi}' geri yüklendi. İşlem öncesi güvenlik yedeği: {guvenlik_yedegi.name}",
        )
    return redirect("yedekleme:yedek_listesi")
