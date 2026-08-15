import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from dersprogrami.models import DersProgrami
from okul.auth import mudur_yardimcisi_required
from okul.models import DersHavuzu, SinifSube
from okul.utils import get_aktif_dp_tarihi, get_aktif_egitim_yili

from .forms import OgrenciAdresForm, OgrenciAyrilmaForm, OgrenciDetayForm, OgrenciForm
from .models import Ogrenci, OgrenciAdres, OgrenciAyrilma, OgrenciDetay, OgrenciMuaf


def _gorunur_ogrenciler_ve_durum(ogrenciler):
    """Mezun/Tasdikname öğrencileri listeden çıkarır, kalanlara `.durum_etiketleri` atar."""
    from secmelidersler.models import OgrenciSinifTekrari, OgrenciTasdikname
    from senesonu.models import SeneSonuOgrenciGecisi

    tasdikname_ids = set(OgrenciTasdikname.objects.values_list("ogrenci_id", flat=True))
    mezun_ids = set(
        SeneSonuOgrenciGecisi.objects.filter(
            durum="mezun", gecis__uygulandi=True
        ).values_list("ogrenci_id", flat=True)
    )

    ogr_listesi = [
        o for o in ogrenciler if o.pk not in tasdikname_ids and o.pk not in mezun_ids
    ]

    # `egitim_yili`ye göre kapsamlanır — aksi hâlde geçmiş bir yılda (örn. 2025-2026)
    # sınıfta kalmış ama o yılı zaten tamamlayıp normal devam eden bir öğrenci de
    # kalıcı olarak "Sınıf Tekrarı" etiketiyle görünür (bkz. commit geçmişi).
    _aktif_yil = get_aktif_egitim_yili()
    sinif_tekrari_qs = OgrenciSinifTekrari.objects.filter(
        ogrenci_id__in=[o.pk for o in ogr_listesi]
    )
    if _aktif_yil:
        sinif_tekrari_qs = sinif_tekrari_qs.filter(egitim_yili=_aktif_yil)
    sinif_tekrari_ids = set(sinif_tekrari_qs.values_list("ogrenci_id", flat=True))

    for ogr in ogr_listesi:
        etiketler = []
        if ogr.pk in sinif_tekrari_ids:
            etiketler.append("Sınıf Tekrarı")
        if not ogr.aktif:
            etiketler.append("Pasif")
        ogr.durum_etiketleri = etiketler

    return ogr_listesi


def _rehberlik_sinif_sube(user):
    """Öğretmenin 'REHBERLİK VE YÖNLENDİRME' dersine ait SinifSube nesnesini döner; yoksa None."""
    try:
        personel = user.personel
    except Exception:
        return None
    _at = get_aktif_dp_tarihi()
    ders = (
        DersProgrami.objects.filter(
            ogretmen=personel,
            ders__ders_adi__iexact="rehberlik ve yönlendirme",
            **({"uygulama_tarihi": _at} if _at else {}),
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
                "ogrenciler": _gorunur_ogrenciler_ve_durum(ogrenciler),
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
            "ogrenciler": _gorunur_ogrenciler_ve_durum(ogrenciler),
            "sinifsube_secenekleri": sinifsube_secenekleri,
            "secili_sinifsube": sinifsube,
            "sinif_filtre_gizli": False,
        },
    )


@login_required
def sureksiz_devamsiz_listesi(request):
    """Öğrenci özel durumları: sürekli devamsız yönetimi."""
    from okul.auth import is_mudur_yardimcisi as _mudur_mi
    gruplar = set(request.user.groups.values_list("name", flat=True))
    yetkili = request.user.is_superuser or _mudur_mi(request.user) or "okul_muduru" in gruplar
    if not yetkili:
        raise PermissionDenied

    if request.method == "POST":
        sureksiz_isaretli = set(request.POST.getlist("sureksiz"))
        sinifsube = request.POST.get("sinifsube_filtre", "")
        qs = Ogrenci.objects.filter(aktif=True)
        if sinifsube:
            try:
                sinif, sube = sinifsube.split("/")
                qs = qs.filter(sinif=sinif.strip(), sube__iexact=sube.strip())
            except ValueError:
                pass
        guncellenen = 0
        for ogr in qs:
            yeni_sureksiz = ogr.okulno in sureksiz_isaretli
            if ogr.sureksiz_devamsiz != yeni_sureksiz:
                ogr.sureksiz_devamsiz = yeni_sureksiz
                ogr.save(update_fields=["sureksiz_devamsiz"])
                guncellenen += 1
        messages.success(request, f"{guncellenen} öğrenci kaydı güncellendi.")
        return redirect(
            request.path + (f"?sinifsube={sinifsube}" if sinifsube else "")
        )

    sinifsube = request.GET.get("sinifsube", "")
    filtre    = request.GET.get("filtre", "")  # "sureksiz" | "muaf" | "" (tümü)

    aktif_yil = get_aktif_egitim_yili()

    ogrenciler = Ogrenci.objects.filter(aktif=True)
    if sinifsube:
        try:
            sinif, sube = sinifsube.split("/")
            ogrenciler = ogrenciler.filter(sinif=sinif.strip(), sube__iexact=sube.strip())
        except ValueError:
            pass
    if filtre == "sureksiz":
        ogrenciler = ogrenciler.filter(sureksiz_devamsiz=True)
    elif filtre == "muaf":
        ogrenciler = ogrenciler.filter(
            muaf_dersler__egitim_yili=aktif_yil
        ).distinct()

    # Muaf ders sayısı per öğrenci (tek sorguda)
    from django.db.models import Count
    muaf_sayilari = {
        r["ogrenci_id"]: r["n"]
        for r in OgrenciMuaf.objects.filter(egitim_yili=aktif_yil)
        .values("ogrenci_id").annotate(n=Count("id"))
    }

    sinifsube_secenekleri = [
        f"{s}/{sb}"
        for s, sb in Ogrenci.objects.filter(aktif=True)
        .values_list("sinif", "sube").distinct().order_by("sinif", "sube")
    ]

    ogr_listesi = list(ogrenciler.order_by("sinif", "sube", "okulno"))
    for ogr in ogr_listesi:
        ogr.muaf_ders_sayisi = muaf_sayilari.get(ogr.pk, 0)

    return render(request, "ogrenci/sureksiz_devamsiz_listesi.html", {
        "ogrenciler":            ogr_listesi,
        "sinifsube_secenekleri": sinifsube_secenekleri,
        "secili_sinifsube":      sinifsube,
        "filtre":                filtre,
        "toplam_sureksiz":       Ogrenci.objects.filter(sureksiz_devamsiz=True, aktif=True).count(),
        "toplam_muaf":           OgrenciMuaf.objects.filter(egitim_yili=aktif_yil).values("ogrenci").distinct().count(),
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


@login_required
def ogrenci_muaf_duzenle(request, pk):
    """Öğrencinin muaf olduğu dersleri (per-ders) düzenler."""
    from okul.auth import is_mudur_yardimcisi as _mudur_mi
    gruplar = set(request.user.groups.values_list("name", flat=True))
    yetkili = request.user.is_superuser or _mudur_mi(request.user) or "okul_muduru" in gruplar
    if not yetkili:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    ogrenci = get_object_or_404(Ogrenci, pk=pk)

    # Aktif sınavdan, öğrencinin sınıf/şubesine ait ders havuzunu çek; yoksa tüm DersHavuzu
    try:
        from ortaksinav_engine.utils import normalize_sube_cell
        from sinav.models import TakvimUretim, Takvim

        aktif_uretim = TakvimUretim.objects.filter(aktif=True).first()
        if aktif_uretim:
            ogrenci_sinifsube = ogrenci.sinifsube.upper().replace(" ", "")
            uygun_ders_ids = {
                ders_id
                for ders_id, subeler in Takvim.objects
                .filter(uretim=aktif_uretim)
                .values_list("ders_id", "subeler")
                if ogrenci_sinifsube in normalize_sube_cell(subeler)
            }
            ders_qs = DersHavuzu.objects.filter(
                pk__in=uygun_ders_ids
            ).order_by("ders_adi") if uygun_ders_ids else DersHavuzu.objects.filter(
                takvim__uretim=aktif_uretim
            ).distinct().order_by("ders_adi")
        else:
            ders_qs = DersHavuzu.objects.all().order_by("ders_adi")
    except Exception:
        ders_qs = DersHavuzu.objects.all().order_by("ders_adi")

    if request.method == "POST":
        aktif_yil = get_aktif_egitim_yili()
        secili_ids = set(map(int, request.POST.getlist("muaf_ders")))
        # Önce bu yılın mevcut muaflarını sil, sonra seçilileri kaydet (önceki yıllar korunur)
        OgrenciMuaf.objects.filter(ogrenci=ogrenci, egitim_yili=aktif_yil).delete()
        yeniler = [
            OgrenciMuaf(ogrenci=ogrenci, ders_id=ders_id, egitim_yili=aktif_yil)
            for ders_id in secili_ids
        ]
        if yeniler:
            OgrenciMuaf.objects.bulk_create(yeniler, ignore_conflicts=True)
        messages.success(
            request,
            f"{ogrenci} için muaf ders listesi güncellendi ({len(yeniler)} ders).",
        )
        redirect_to = request.POST.get("next")
        if redirect_to:
            return redirect(redirect_to)
        return redirect("ogrenci:sureksiz_devamsiz_listesi")

    mevcut_ders_ids = set(
        OgrenciMuaf.objects.filter(
            ogrenci=ogrenci, egitim_yili=get_aktif_egitim_yili()
        ).values_list("ders_id", flat=True)
    )

    return render(
        request,
        "ogrenci/ogrenci_muaf_duzenle.html",
        {
            "ogrenci": ogrenci,
            "dersler": ders_qs,
            "mevcut_ders_ids": mevcut_ders_ids,
        },
    )


# ─────────────────────────────────────────────
# Yeni Kayıt — sınıf/şube bazlı öğrenci CRUD'u
# ─────────────────────────────────────────────


def _yeni_kayit_ogrenci_qs(sinif, sube=None):
    """'Yeni kayıt' öğrenci tanımı: aktif (ayrılma kaydı olan öğrenci `Ogrenci.aktif`
    False'a düşer — bkz. `ayrilma_ekle`), VE sınıf tekrarı OLMAYAN öğrenciler.
    Sınıf tekrarı yapan bir öğrenci (bkz. `OgrenciSinifTekrari`, aktif yıla göre)
    devam eden bir kayıttır, yeni kayıt değildir — kendi seçmeli/zorunlu ders
    ataması `secmeli:sinif_tekrari_listesi` / `secmeli:sinif_dagilimi` akışlarından
    yürütülür, bu ekranla karıştırılmamalı (bkz. commit geçmişi).
    """
    from secmelidersler.models import OgrenciSinifTekrari

    qs = Ogrenci.objects.filter(sinif=sinif, aktif=True)
    if sube:
        qs = qs.filter(sube__iexact=sube)

    aktif_yil = get_aktif_egitim_yili()
    tekrar_qs = OgrenciSinifTekrari.objects.filter(ogrenci__sinif=sinif)
    if aktif_yil:
        tekrar_qs = tekrar_qs.filter(egitim_yili=aktif_yil)
    tekrar_ids = set(tekrar_qs.values_list("ogrenci_id", flat=True))

    return qs.exclude(pk__in=tekrar_ids)


@mudur_yardimcisi_required
def yeni_kayit_hub(request, sinif):
    subeler = sorted(
        set(SinifSube.objects.filter(sinif=sinif).values_list("sube", flat=True))
        | set(Ogrenci.objects.filter(sinif=sinif).values_list("sube", flat=True).distinct())
    )
    sinifsube_map = {ss.sube: ss for ss in SinifSube.objects.filter(sinif=sinif)}

    sube_verileri = [
        {
            "sube": sube,
            "toplam": _yeni_kayit_ogrenci_qs(sinif, sube).count(),
            "acik": sinifsube_map[sube].acik_mi() if sube in sinifsube_map else True,
        }
        for sube in subeler
    ]

    return render(request, "ogrenci/yeni_kayit_hub.html", {
        "title": f"{sinif}. Sınıf Yeni Kayıt",
        "sinif": sinif,
        "sube_verileri": sube_verileri,
        "toplam_ogrenci": sum(s["toplam"] for s in sube_verileri),
    })


def _sube_acik_mi(sinif, sube):
    """SinifSube kaydı yoksa (henüz tanımlanmamış şube) açık kabul edilir. Açık/kapalı
    durumu aktif eğitim-öğretim yılına göre değerlendirilir — bkz. SinifSube.acik_mi."""
    kayit = SinifSube.objects.filter(sinif=sinif, sube__iexact=sube).first()
    return kayit.acik_mi() if kayit else True


@mudur_yardimcisi_required
def yeni_kayit_liste(request, sinif, sube):
    sube = sube.upper()
    ogrenciler = _yeni_kayit_ogrenci_qs(sinif, sube).order_by("okulno")

    return render(request, "ogrenci/yeni_kayit_liste.html", {
        "title": f"{sinif}/{sube} — Öğrenciler",
        "sinif": sinif,
        "sube": sube,
        "ogrenciler": ogrenciler,
        "acik": _sube_acik_mi(sinif, sube),
    })


@mudur_yardimcisi_required
def yeni_kayit_ekle(request, sinif, sube):
    sube = sube.upper()

    if not _sube_acik_mi(sinif, sube):
        messages.error(request, f"{sinif}/{sube} şubesi kapalı — yeni öğrenci eklenemez.")
        return redirect("ogrenci:yeni_kayit_liste", sinif=sinif, sube=sube)

    if request.method == "POST":
        form = OgrenciForm(request.POST)
        if form.is_valid():
            ogrenci = form.save(commit=False)
            ogrenci.sinif = sinif
            ogrenci.sube = sube
            ogrenci.save()
            messages.success(request, f"{ogrenci.adi} {ogrenci.soyadi} eklendi.")
            return redirect("ogrenci:yeni_kayit_liste", sinif=sinif, sube=sube)
    else:
        form = OgrenciForm()

    return render(request, "ogrenci/yeni_kayit_form.html", {
        "title": f"{sinif}/{sube} — Yeni Öğrenci Ekle",
        "sinif": sinif,
        "sube": sube,
        "form": form,
        "duzenleme": False,
    })


@mudur_yardimcisi_required
def yeni_kayit_duzenle(request, pk):
    ogrenci = get_object_or_404(Ogrenci, pk=pk)

    if request.method == "POST":
        form = OgrenciForm(request.POST, instance=ogrenci)
        if form.is_valid():
            form.save()
            messages.success(request, f"{ogrenci.adi} {ogrenci.soyadi} güncellendi.")
            return redirect("ogrenci:yeni_kayit_liste", sinif=ogrenci.sinif, sube=ogrenci.sube)
    else:
        form = OgrenciForm(instance=ogrenci)

    return render(request, "ogrenci/yeni_kayit_form.html", {
        "title": f"{ogrenci.adi} {ogrenci.soyadi} — Düzenle",
        "sinif": ogrenci.sinif,
        "sube": ogrenci.sube,
        "form": form,
        "duzenleme": True,
        "ogrenci": ogrenci,
    })


@mudur_yardimcisi_required
def yeni_kayit_sil(request, pk):
    if request.method != "POST":
        return redirect("ogrenci:ogrenci_liste")

    ogrenci = get_object_or_404(Ogrenci, pk=pk)
    sinif, sube = ogrenci.sinif, ogrenci.sube
    ad = f"{ogrenci.adi} {ogrenci.soyadi}"
    ogrenci.delete()
    messages.success(request, f"{ad} silindi.")
    return redirect("ogrenci:yeni_kayit_liste", sinif=sinif, sube=sube)


# ─────────────────────────────────────────────
# Okuldan Ayrılma Bilgileri CRUD
# (Nakil, Öğrenim Hakkını Tamamladı, Mesem, Yurt Dışı, Vefat, Diğer)
# ─────────────────────────────────────────────


@mudur_yardimcisi_required
def ayrilma_listesi(request):
    from django.db.models import Q

    kayitlar = (
        OgrenciAyrilma.objects
        .select_related("ogrenci")
        .order_by("ogrenci__sinif", "ogrenci__sube", "ogrenci__okulno")
    )

    sebep_filtre = request.GET.get("sebep", "")
    if sebep_filtre:
        kayitlar = kayitlar.filter(sebep=sebep_filtre)

    arama = request.GET.get("q", "").strip()
    arama_sonuclari = []
    if arama:
        mevcut_ids = set(
            OgrenciAyrilma.objects.values_list("ogrenci_id", flat=True)
        )
        arama_sonuclari = list(
            Ogrenci.objects.filter(
                Q(okulno__icontains=arama)
                | Q(adi__icontains=arama)
                | Q(soyadi__icontains=arama),
                aktif=True,
            ).exclude(pk__in=mevcut_ids).order_by("sinif", "sube", "okulno")[:20]
        )

    return render(request, "ogrenci/ayrilma_listesi.html", {
        "title": "Okuldan Ayrılma Bilgileri",
        "kayitlar": kayitlar,
        "sebep_filtre": sebep_filtre,
        "sebep_secenekleri": OgrenciAyrilma._meta.get_field("sebep").choices,
        "arama": arama,
        "arama_sonuclari": arama_sonuclari,
        "toplam": kayitlar.count(),
    })


@mudur_yardimcisi_required
def ayrilma_ekle(request):
    if request.method != "POST":
        return redirect("ogrenci:ayrilma_listesi")

    ogrenci_pk = request.POST.get("ogrenci_pk")
    ogr = Ogrenci.objects.filter(pk=ogrenci_pk).first()
    if not ogr:
        messages.error(request, "Öğrenci bulunamadı.")
        return redirect("ogrenci:ayrilma_listesi")

    if OgrenciAyrilma.objects.filter(ogrenci=ogr).exists():
        messages.warning(request, f"{ogr.adi} {ogr.soyadi} için zaten bir ayrılma kaydı var.")
        return redirect("ogrenci:ayrilma_listesi")

    form = OgrenciAyrilmaForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Ayrılma sebebi seçilmedi ya da form geçersiz.")
        return redirect("ogrenci:ayrilma_listesi")

    ayrilma = form.save(commit=False)
    ayrilma.ogrenci = ogr
    ayrilma.egitim_yili = get_aktif_egitim_yili()
    ayrilma.save()

    if ogr.aktif:
        ogr.aktif = False
        ogr.save(update_fields=["aktif"])

    messages.success(
        request,
        f"{ogr.adi} {ogr.soyadi} — {ayrilma.get_sebep_display()} olarak kaydedildi ve "
        "aktif öğrenci listelerinden çıkarıldı.",
    )
    from django.urls import reverse as _rev
    q = request.POST.get("q", "")
    return redirect(f"{_rev('ogrenci:ayrilma_listesi')}?q={q}")


@mudur_yardimcisi_required
def ayrilma_duzenle(request, pk):
    ayrilma = get_object_or_404(OgrenciAyrilma.objects.select_related("ogrenci"), pk=pk)

    if request.method == "POST":
        form = OgrenciAyrilmaForm(request.POST, instance=ayrilma)
        if form.is_valid():
            form.save()
            messages.success(request, f"{ayrilma.ogrenci} ayrılma kaydı güncellendi.")
            return redirect("ogrenci:ayrilma_listesi")
    else:
        form = OgrenciAyrilmaForm(instance=ayrilma)

    return render(request, "ogrenci/ayrilma_form.html", {
        "title": f"{ayrilma.ogrenci} — Ayrılma Kaydını Düzenle",
        "form": form,
        "ayrilma": ayrilma,
    })


@mudur_yardimcisi_required
def ayrilma_sil(request, pk):
    if request.method == "POST":
        kayit = OgrenciAyrilma.objects.filter(pk=pk).select_related("ogrenci").first()
        if kayit:
            ogr = kayit.ogrenci
            ad = f"{ogr.adi} {ogr.soyadi}"
            kayit.delete()
            if not ogr.aktif:
                ogr.aktif = True
                ogr.save(update_fields=["aktif"])
            messages.success(
                request, f"{ad} ayrılma kaydından çıkarıldı ve tekrar aktif hale getirildi."
            )
    return redirect("ogrenci:ayrilma_listesi")
