import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from dersprogrami.models import DersProgrami

from .forms import OgrenciAdresForm, OgrenciDetayForm
from .models import Ogrenci, OgrenciAdres, OgrenciDetay


def _rehberlik_sinif_sube(user):
    """Öğretmenin 'REHBERLİK VE YÖNLENDİRME' dersine ait SinifSube nesnesini döner; yoksa None."""
    try:
        personel = user.personel
    except Exception:
        return None
    ders = (
        DersProgrami.objects.filter(
            ogretmen=personel,
            ders__ders_adi__iexact="rehberlik ve yönlendirme",
        )
        .select_related("sinif_sube", "ders")
        .first()
    )
    return ders.sinif_sube if ders else None


def _only_ogretmen(user):
    if user.is_superuser:
        return False
    gruplar = set(user.groups.values_list("name", flat=True))
    yonetici = {"mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"}
    return "ogretmen" in gruplar and not (gruplar & yonetici)


EXCEL_SUTUNLAR = [
    "okulno",
    "sinif",
    "sube",
    "tckimlikno",
    "adi",
    "soyadi",
    "dogumtarihi",
    "cinsiyet",
    "babaadi",
    "anneadi",
    "veli",
    "velitelefon",
    "annetelefon",
    "babatelefon",
    "il",
    "ilce",
    "mahalle",
    "postakodu",
    "adres",
]

ZORUNLU_SUTUNLAR = [
    "okulno",
    "sinif",
    "sube",
    "tckimlikno",
    "adi",
    "soyadi",
    "dogumtarihi",
    "cinsiyet",
]

CINSIYET_MAP = {
    "e": "E",
    "erkek": "E",
    "bay": "E",
    "male": "E",
    "m": "E",
    "k": "K",
    "kız": "K",
    "kiz": "K",
    "bayan": "K",
    "female": "K",
    "f": "K",
}


def normalize_cinsiyet(deger):
    if not deger:
        return None
    return CINSIYET_MAP.get(deger.strip().lower())


@login_required
def excel_yukle(request):
    if request.method == "POST":
        dosya = request.FILES.get("excel_dosya")
        if not dosya:
            messages.error(request, "Lütfen bir Excel dosyası seçin.")
            return redirect("ogrenci:excel_yukle")

        try:
            df = pd.read_excel(dosya, dtype=str)
            df.columns = [c.strip().lower() for c in df.columns]
        except Exception as e:
            messages.error(request, f"Dosya okunamadı: {e}")
            return redirect("ogrenci:excel_yukle")

        eksik = [s for s in ZORUNLU_SUTUNLAR if s not in df.columns]
        if eksik:
            messages.error(request, f"Eksik sütunlar: {', '.join(eksik)}")
            return redirect("ogrenci:excel_yukle")

        eklenen = guncellenen = hatali = 0

        for i, satir in df.iterrows():

            def col(ad):
                val = satir.get(ad, None)
                if pd.isna(val) if val is not None else True:
                    return None
                return str(val).strip() or None

            try:
                with transaction.atomic():
                    ogrenci, olusturuldu = Ogrenci.objects.update_or_create(
                        tckimlikno=col("tckimlikno"),
                        defaults={
                            "okulno": col("okulno"),
                            "sinif": int(col("sinif")),
                            "sube": col("sube"),
                            "adi": col("adi"),
                            "soyadi": col("soyadi"),
                            "dogumtarihi": pd.to_datetime(col("dogumtarihi")).date(),
                            "cinsiyet": normalize_cinsiyet(col("cinsiyet")),
                        },
                    )

                    OgrenciDetay.objects.update_or_create(
                        ogrenci=ogrenci,
                        defaults={
                            "babaadi": col("babaadi"),
                            "anneadi": col("anneadi"),
                            "veli": col("veli"),
                            "velitelefon": col("velitelefon"),
                            "annetelefon": col("annetelefon"),
                            "babatelefon": col("babatelefon"),
                        },
                    )

                    OgrenciAdres.objects.update_or_create(
                        ogrenci=ogrenci,
                        defaults={
                            "il": col("il"),
                            "ilce": col("ilce"),
                            "mahalle": col("mahalle"),
                            "postakodu": col("postakodu"),
                            "adres": col("adres"),
                        },
                    )

                    if olusturuldu:
                        eklenen += 1
                    else:
                        guncellenen += 1

            except Exception as e:
                hatali += 1
                messages.warning(request, f"Satır {i + 2} atlandı: {e}")

        messages.success(
            request,
            f"{eklenen} yeni kayıt eklendi, {guncellenen} kayıt güncellendi, {hatali} satır hatalı.",
        )
        return redirect("ogrenci:excel_yukle")

    return render(request, "ogrenci/excel_yukle.html")


@login_required
def ogrenci_liste(request):
    # Ogretmen: yalnızca kendi sınıf rehberliği sınıfını görebilir
    if _only_ogretmen(request.user):
        ss = _rehberlik_sinif_sube(request.user)
        if not ss:
            messages.error(
                request, "Sınıf rehberliği atanmamış, öğrenci listesine erişiminiz bulunmamaktadır."
            )
            return redirect("index")
        ogrenciler = Ogrenci.objects.filter(sinif=ss.sinif, sube__iexact=ss.sube).order_by("okulno")
        return render(
            request,
            "ogrenci/ogrenci_liste.html",
            {
                "ogrenciler": ogrenciler,
                "sinifsube_secenekleri": [],
                "secili_sinifsube": str(ss),
                "sinif_filtre_gizli": True,
            },
        )

    sinifsube = request.GET.get("sinifsube")

    ogrenciler = Ogrenci.objects.all()
    if sinifsube:
        try:
            sinif, sube = sinifsube.split("/")
            ogrenciler = ogrenciler.filter(sinif=sinif.strip(), sube__iexact=sube.strip())
        except ValueError:
            pass

    sinifsube_listesi = (
        Ogrenci.objects.values_list("sinif", "sube").distinct().order_by("sinif", "sube")
    )
    sinifsube_secenekleri = [f"{s}/{sb}" for s, sb in sinifsube_listesi]

    return render(
        request,
        "ogrenci/ogrenci_liste.html",
        {
            "ogrenciler": ogrenciler,
            "sinifsube_secenekleri": sinifsube_secenekleri,
            "secili_sinifsube": sinifsube,
            "sinif_filtre_gizli": False,
        },
    )


@login_required
def sureksiz_devamsiz_listesi(request):
    """Öğrenci özel durumları: sürekli devamsız ve muaf yönetimi."""
    from okul.auth import is_mudur_yardimcisi as _mudur_mi
    gruplar = set(request.user.groups.values_list("name", flat=True))
    yetkili = request.user.is_superuser or _mudur_mi(request.user) or "okul_muduru" in gruplar
    if not yetkili:
        raise PermissionDenied

    if request.method == "POST":
        sureksiz_isaretli = set(request.POST.getlist("sureksiz"))
        muaf_isaretli     = set(request.POST.getlist("muaf"))
        sinifsube = request.POST.get("sinifsube_filtre", "")
        qs = Ogrenci.objects.all()
        if sinifsube:
            try:
                sinif, sube = sinifsube.split("/")
                qs = qs.filter(sinif=sinif.strip(), sube__iexact=sube.strip())
            except ValueError:
                pass
        guncellenen = 0
        for ogr in qs:
            yeni_sureksiz = ogr.okulno in sureksiz_isaretli
            yeni_muaf     = ogr.okulno in muaf_isaretli
            fields = []
            if ogr.sureksiz_devamsiz != yeni_sureksiz:
                ogr.sureksiz_devamsiz = yeni_sureksiz
                fields.append("sureksiz_devamsiz")
            if ogr.muaf != yeni_muaf:
                ogr.muaf = yeni_muaf
                fields.append("muaf")
            if fields:
                ogr.save(update_fields=fields)
                guncellenen += 1
        messages.success(request, f"{guncellenen} öğrenci kaydı güncellendi.")
        return redirect(
            request.path + (f"?sinifsube={sinifsube}" if sinifsube else "")
        )

    sinifsube = request.GET.get("sinifsube", "")
    filtre    = request.GET.get("filtre", "")  # "sureksiz" | "muaf" | "" (tümü)

    ogrenciler = Ogrenci.objects.all()
    if sinifsube:
        try:
            sinif, sube = sinifsube.split("/")
            ogrenciler = ogrenciler.filter(sinif=sinif.strip(), sube__iexact=sube.strip())
        except ValueError:
            pass
    if filtre == "sureksiz":
        ogrenciler = ogrenciler.filter(sureksiz_devamsiz=True)
    elif filtre == "muaf":
        ogrenciler = ogrenciler.filter(muaf=True)

    sinifsube_secenekleri = [
        f"{s}/{sb}"
        for s, sb in Ogrenci.objects.values_list("sinif", "sube").distinct().order_by("sinif", "sube")
    ]

    return render(request, "ogrenci/sureksiz_devamsiz_listesi.html", {
        "ogrenciler":            ogrenciler.order_by("sinif", "sube", "okulno"),
        "sinifsube_secenekleri": sinifsube_secenekleri,
        "secili_sinifsube":      sinifsube,
        "filtre":                filtre,
        "toplam_sureksiz":       Ogrenci.objects.filter(sureksiz_devamsiz=True).count(),
        "toplam_muaf":           Ogrenci.objects.filter(muaf=True).count(),
    })


@login_required
@require_POST
def sureksiz_devamsiz_toggle(request, pk):
    """Tek öğrencinin sureksiz_devamsiz bayrağını tersine çevirir (AJAX)."""
    from okul.auth import is_mudur_yardimcisi as _mudur_mi
    gruplar = set(request.user.groups.values_list("name", flat=True))
    yetkili = request.user.is_superuser or _mudur_mi(request.user) or "okul_muduru" in gruplar
    if not yetkili:
        return JsonResponse({"ok": False, "hata": "Yetkisiz"}, status=403)

    ogr = get_object_or_404(Ogrenci, pk=pk)
    ogr.sureksiz_devamsiz = not ogr.sureksiz_devamsiz
    ogr.save(update_fields=["sureksiz_devamsiz"])
    return JsonResponse({"ok": True, "sureksiz": ogr.sureksiz_devamsiz})


@login_required
def ogrenci_detay_duzenle(request, pk):
    ogrenci = get_object_or_404(Ogrenci, pk=pk)

    # Ogretmen: yalnızca kendi sınıf rehberliği sınıfındaki öğrenciyi düzenleyebilir
    if _only_ogretmen(request.user):
        ss = _rehberlik_sinif_sube(request.user)
        if not ss or ogrenci.sinif != ss.sinif or ogrenci.sube.upper() != ss.sube.upper():
            raise PermissionDenied

    detay, _ = OgrenciDetay.objects.get_or_create(ogrenci=ogrenci)
    adres, _ = OgrenciAdres.objects.get_or_create(ogrenci=ogrenci)

    if request.method == "POST":
        detay_form = OgrenciDetayForm(request.POST, instance=detay)
        adres_form = OgrenciAdresForm(request.POST, instance=adres)
        if detay_form.is_valid() and adres_form.is_valid():
            detay_form.save()
            adres_form.save()
            messages.success(request, f"{ogrenci} bilgileri güncellendi.")
            return redirect("ogrenci:ogrenci_liste")
    else:
        detay_form = OgrenciDetayForm(instance=detay)
        adres_form = OgrenciAdresForm(instance=adres)

    return render(
        request,
        "ogrenci/ogrenci_detay_duzenle.html",
        {
            "ogrenci": ogrenci,
            "detay_form": detay_form,
            "adres_form": adres_form,
        },
    )
