from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from ogrenci.services.rehberlik import rehberlik_sinif_sube
from okul.auth import is_ust_yonetici, ust_yonetici_required
from okul.models import SinifSube
from okul.utils import get_aktif_egitim_yili
from veriaktar.services.sosyalkulup_import_service import (
    SosyalKulupExcelHatasi,
    sosyal_kulupleri_ice_aktar,
)

from .models import SosyalKulup
from .services.kulup import (
    kulup_danismani_mi,
    kulup_danismanlari,
    kulup_ozetleri,
    kulup_uyeleri,
)
from .services.uyelik import (
    secilebilir_kulupler,
    sinif_kuluplerini_kaydet,
    sinif_ogrencileri,
    sinif_uyelikleri,
)


def _secili_sinif_sube(request):
    """Müdür yardımcısı/okul müdürü istediği sınıfı seçer (?sinif_sube=<pk>); diğer
    kullanıcılar yalnızca sınıf rehber öğretmeni oldukları sınıfı görür."""
    if is_ust_yonetici(request.user):
        pk = request.POST.get("sinif_sube") or request.GET.get("sinif_sube")
        if pk and str(pk).isdigit():
            return SinifSube.objects.filter(pk=pk).first()
        return None
    return rehberlik_sinif_sube(request.user)


@login_required
def ogrenci_kulup_belirle(request):
    ust_yonetici = is_ust_yonetici(request.user)
    ss = _secili_sinif_sube(request)
    if ss is None and not ust_yonetici:
        messages.error(
            request, "Sınıf rehberliği atanmamış, öğrenci kulübü belirleme yetkiniz bulunmamaktadır."
        )
        return redirect("index")

    egitim_yili = get_aktif_egitim_yili()
    if ss is not None and egitim_yili is not None and request.method == "POST":
        secimler = {}
        gecersiz = False
        for anahtar, deger in request.POST.items():
            if not anahtar.startswith("kulup_"):
                continue
            ogrenci_id = anahtar.removeprefix("kulup_")
            if not ogrenci_id.isdigit() or (deger and not deger.isdigit()):
                gecersiz = True
                break
            secimler[int(ogrenci_id)] = int(deger) if deger else None
        try:
            if gecersiz:
                raise ValueError
            eklenen, guncellenen, silinen = sinif_kuluplerini_kaydet(
                ss.sinif, ss.sube, secimler, egitim_yili
            )
        except ValueError:
            messages.error(request, "Geçersiz kulüp seçimi; hiçbir değişiklik kaydedilmedi.")
        else:
            if eklenen or guncellenen or silinen:
                messages.success(
                    request,
                    f"{ss} kulüp bilgileri kaydedildi "
                    f"({eklenen} eklendi, {guncellenen} değişti, {silinen} kaldırıldı).",
                )
            else:
                messages.info(request, "Değişiklik yapılmadı.")
        url = request.path
        if ust_yonetici:
            url += f"?sinif_sube={ss.pk}"
        return redirect(url)

    satirlar, kulupler = [], []
    if ss is not None and egitim_yili is not None:
        uyelikler = sinif_uyelikleri(ss.sinif, ss.sube, egitim_yili)
        satirlar = [(ogr, uyelikler.get(ogr.pk)) for ogr in sinif_ogrencileri(ss.sinif, ss.sube)]
        kulupler = secilebilir_kulupler(u.kulup_id for u in uyelikler.values())

    return render(
        request,
        "sosyalkulup/ogrenci_kulup_belirle.html",
        {
            "sinif_sube": ss,
            "egitim_yili": egitim_yili,
            "satirlar": satirlar,
            "kulupler": kulupler,
            "sinif_secimi": ust_yonetici,
            "sinif_sube_secenekleri": (
                SinifSube.objects.order_by("sinif", "sube") if ust_yonetici else []
            ),
        },
    )


@ust_yonetici_required
def kulup_listesi(request):
    egitim_yili = get_aktif_egitim_yili()
    return render(
        request,
        "sosyalkulup/kulup_listesi.html",
        {
            "egitim_yili": egitim_yili,
            "kulupler": kulup_ozetleri(egitim_yili) if egitim_yili else [],
        },
    )


@ust_yonetici_required
def kulup_excel_yukle(request):
    egitim_yili = get_aktif_egitim_yili()
    sonuc = None
    if request.method == "POST":
        dosya = request.FILES.get("dosya")
        if egitim_yili is None:
            messages.error(request, "Aktif eğitim-öğretim yılı tanımlı değil.")
        elif not dosya:
            messages.error(request, "Lütfen bir Excel dosyası seçin.")
        else:
            try:
                sonuc = sosyal_kulupleri_ice_aktar(dosya, egitim_yili)
            except SosyalKulupExcelHatasi as exc:
                messages.error(request, str(exc))
    return render(
        request,
        "sosyalkulup/kulup_excel_yukle.html",
        {"egitim_yili": egitim_yili, "sonuc": sonuc},
    )


@login_required
def kulup_ogrencileri(request, pk):
    kulup = get_object_or_404(SosyalKulup, pk=pk)
    egitim_yili = get_aktif_egitim_yili()
    if not (is_ust_yonetici(request.user) or kulup_danismani_mi(request.user, kulup, egitim_yili)):
        raise PermissionDenied
    return render(
        request,
        "sosyalkulup/kulup_ogrencileri.html",
        {
            "kulup": kulup,
            "egitim_yili": egitim_yili,
            "danismanlar": kulup_danismanlari(kulup, egitim_yili),
            "uyelikler": kulup_uyeleri(kulup, egitim_yili),
        },
    )
