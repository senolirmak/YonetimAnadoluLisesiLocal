from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from dersprogrami.models import DersProgrami
from nobet.models import NobetGorevi, NobetPersonel
from okul.models import SinifSube
from okul.models import OkulBilgi

from .forms import (
    DersProgramiImportForm,
    NobetImportForm,
    OgrenciImportForm,
    OkulBilgiForm,
    PersonelImportForm,
    SinifSubeImportForm,
)
from okul.auth import mudur_yardimcisi_required

from .services.default_path_service import DefaultPath
from .services.ders_programi_import_service import DersProgramiIsleyici
from .services.nobet_import_service import NobetIsleyici
from .services.ogrenci_import_service import OgrenciIsleyici
from .services.personel_import_service import PersonelIsleyici
from .services.sinifsube_import_service import sinif_sube_kaydet


def _save_file(f, dp):
    file_path = dp.VERI_DIR / f.name
    with open(file_path, "wb+") as dest:
        for chunk in f.chunks():
            dest.write(chunk)
    return file_path


@login_required
@mudur_yardimcisi_required
def veriaktar_ana(request):
    mevcut_okul = OkulBilgi.objects.first()
    okul_initial = {
        "okul_kodu": mevcut_okul.okul_kodu if mevcut_okul else "",
        "okul_adi": mevcut_okul.okul_adi if mevcut_okul else "",
        "okul_muduru": mevcut_okul.okul_muduru if mevcut_okul else "",
    }

    mevcut_siniflar = defaultdict(list)
    if not SinifSube.objects.exists():
        defaults = {
            9: ["A", "B", "C", "D", "E", "F"],
            10: ["A", "B", "C", "D", "E", "F", "G", "H", "İ"],
            11: ["A", "B", "C", "D", "E", "F", "G", "H"],
            12: ["A", "B", "C", "D", "E", "F", "G"],
        }
        for k, v in defaults.items():
            mevcut_siniflar[k] = v
    else:
        for s in SinifSube.objects.all().order_by("sinif", "sube"):
            mevcut_siniflar[s.sinif].append(s.sube)
    sinif_initial = {f"sinif_{k}": ",".join(v) for k, v in mevcut_siniflar.items()}

    okul_form = OkulBilgiForm(request.POST or None, prefix="okul", initial=okul_initial)
    personel_form = PersonelImportForm(
        request.POST or None, request.FILES or None, prefix="personel"
    )
    sinif_form = SinifSubeImportForm(request.POST or None, prefix="sinif", initial=sinif_initial)
    ders_form = DersProgramiImportForm(request.POST or None, request.FILES or None, prefix="ders")
    nobet_form = NobetImportForm(request.POST or None, request.FILES or None, prefix="nobet")
    ogrenci_form = OgrenciImportForm(request.POST or None, request.FILES or None, prefix="ogrenci")

    if request.method == "POST":
        dp = DefaultPath()
        try:
            if "okul_bilgi_aktar" in request.POST and okul_form.is_valid():
                OkulBilgi.objects.update_or_create(
                    id=1,
                    defaults={
                        "okul_kodu": okul_form.cleaned_data["okul_kodu"],
                        "okul_adi": okul_form.cleaned_data["okul_adi"],
                        "okul_muduru": okul_form.cleaned_data["okul_muduru"],
                    },
                )
                messages.success(request, "Okul bilgileri başarıyla kaydedildi.")

            elif "personel_aktar" in request.POST and personel_form.is_valid():
                f = request.FILES["personel-dosya"]
                tarih = personel_form.cleaned_data["uygulama_tarihi"]
                file_path = _save_file(f, dp)
                PersonelIsleyici(personel_path=str(file_path), uygulama_tarihi=tarih, kullanici=request.user).calistir()
                messages.success(request, "Personel listesi başarıyla aktarıldı.")

            elif "sinif_sube_aktar" in request.POST and sinif_form.is_valid():
                sinif_bilgileri = {}
                for level in [9, 10, 11, 12]:
                    raw = sinif_form.cleaned_data.get(f"sinif_{level}", "")
                    sinif_bilgileri[level] = [
                        s.strip().upper() for s in raw.split(",") if s.strip()
                    ]
                sinif_sube_kaydet(sinif_bilgileri)
                messages.success(request, "Sınıf ve şube bilgileri başarıyla güncellendi.")

            elif "ders_programi_aktar" in request.POST and ders_form.is_valid():
                f = request.FILES["ders-dosya"]
                tarih = ders_form.cleaned_data["uygulama_tarihi"]
                file_path = _save_file(f, dp)
                DersProgramiIsleyici(file_path=str(file_path), uygulama_tarihi=tarih, kullanici=request.user).calistir()
                messages.success(request, "Ders programı başarıyla aktarıldı.")

            elif "nobet_aktar" in request.POST and nobet_form.is_valid():
                f = request.FILES["nobet-dosya"]
                tarih = nobet_form.cleaned_data["uygulama_tarihi"]
                file_path = _save_file(f, dp)
                NobetIsleyici(nobet_path=str(file_path), uygulama_tarihi=tarih, kullanici=request.user).calistir()
                messages.success(request, "Nöbetçi listesi başarıyla aktarıldı.")

            elif "ogrenci_aktar" in request.POST and ogrenci_form.is_valid():
                f = request.FILES["ogrenci-dosya"]
                dosya_tarihi = ogrenci_form.cleaned_data.get("dosya_tarihi")
                file_path = _save_file(f, dp)
                sonuc = OgrenciIsleyici(file_path=str(file_path), kullanici=request.user, dosya_tarihi=dosya_tarihi).calistir()
                messages.success(
                    request,
                    f"Öğrenci listesi aktarıldı — "
                    f"{sonuc['yeni']} yeni, {sonuc['guncellenen']} güncellendi"
                    + (f", {sonuc['hatali']} hatalı" if sonuc["hatali"] else "") + ".",
                )

        except Exception as e:
            messages.error(request, f"Hata oluştu: {str(e)}")

        return redirect(request.path)

    from ogrenci.models import Ogrenci as OgrenciModel

    adimlar = [
        OkulBilgi.objects.exists(),
        NobetPersonel.objects.exists(),
        SinifSube.objects.exists(),
        DersProgrami.objects.exists(),
        NobetGorevi.objects.exists(),
        OgrenciModel.objects.exists(),
    ]
    tamamlanan = sum(adimlar)
    aktif_adim = next((i + 1 for i, done in enumerate(adimlar) if not done), 7)

    return render(
        request,
        "veriaktar/veriaktar_ana.html",
        {
            "title": "Veri Aktarım Merkezi",
            "okul_form": okul_form,
            "personel_form": personel_form,
            "sinif_form": sinif_form,
            "ders_form": ders_form,
            "nobet_form": nobet_form,
            "ogrenci_form": ogrenci_form,
            "adimlar": adimlar,
            "tamamlanan": tamamlanan,
            "aktif_adim": aktif_adim,
        },
    )
