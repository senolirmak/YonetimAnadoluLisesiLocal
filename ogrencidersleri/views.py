from io import BytesIO

from django.contrib import messages
from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from okul.auth import mudur_yardimcisi_required
from okul.models import OkulBilgi
from ogrenci.models import Ogrenci
from secmelidersler.models import (
    Alan, AlanDers, OgrenciSinifTekrari, OgrenciTasdikname, OrtakDers, SecmeliDersGrubu,
    get_toplam_saat, get_toplam_saat_map, get_aktif_egitim_yili, _VARSAYILAN_TOPLAM_SAAT,
)
from secmelidersler.services.pdf_rapor import secmeli_ders_pdf

from .forms import OgrenciSecmeliDersForm
from .models import OgrenciSecmeliDers, OgrenciZorunluDers

_GELECEK = lambda sinif: sinif + 1


def _yf(qs, aktif_yil, alan="egitim_yili"):
    return qs.filter(**{alan: aktif_yil}) if aktif_yil else qs


def _secili_yil(request, aktif_yil):
    """?yil=<pk> verilmişse o EgitimOgretimYili'ni, yoksa aktif_yil'i döner."""
    from okul.models import EgitimOgretimYili

    yil_pk = request.GET.get("yil", "").strip()
    if yil_pk:
        secili = EgitimOgretimYili.objects.filter(pk=yil_pk).first()
        if secili:
            return secili
    return aktif_yil


def _secilebilir_yillar(aktif_yil):
    """Yıl seçici dropdown'ında gösterilecek yıllar: aktif yıl her zaman, geçmiş bir yıl ise
    ondan başlayan UYGULANMIŞ bir sene sonu geçişi varsa (yalnızca o zaman geçmiş kohort
    SeneSonuOgrenciGecisi üzerinden yeniden kurulabilir)."""
    from okul.models import EgitimOgretimYili
    from senesonu.models import SeneSonuGecisi

    yil_ids = set(
        SeneSonuGecisi.objects.filter(uygulandi=True).values_list("eski_egitim_yili_id", flat=True)
    )
    if aktif_yil:
        yil_ids.add(aktif_yil.pk)
    return EgitimOgretimYili.objects.filter(pk__in=yil_ids).order_by("egitim_yili")


def _sinif_tekrari_ids(ogr_ids, aktif_yil=None):
    """OgrenciSinifTekrari modeline kayıtlı öğrenci pk seti.

    `OgrenciSinifTekrari.egitim_yili` — bir öğrencinin HANGİ eğitim-öğretim yılında
    sınıfta kaldığını taşır (bkz. commit geçmişi: bu alan var olduğu hâlde burada
    hiç kullanılmıyordu, bu yüzden geçen yıl (örn. 2025-2026) sınıfta kalmış ama bu
    yıl (2026-2027) normal devam eden bir öğrenci, aktif yılın tam listesinde hâlâ
    "Tekrar" olarak görünüyor ve gelecek_sinif hesabı yanlış çıkıyordu). `aktif_yil`
    verildiğinde yalnızca O YILA ait tekrar kayıtları sayılır; verilmezse (örn.
    `_gecmis_yil_ogr_listesi`'nin kendi yıl-bazlı mantığı zaten yeterli olduğu
    durumlar) yıl kısıtı uygulanmaz.
    """
    qs = OgrenciSinifTekrari.objects.filter(ogrenci_id__in=ogr_ids)
    if aktif_yil:
        qs = qs.filter(egitim_yili=aktif_yil)
    return set(qs.values_list("ogrenci_id", flat=True))


def _tasdikname_ids(ogr_ids):
    """Tasdikname kaydı olan öğrenci pk seti."""
    return set(
        OgrenciTasdikname.objects.filter(
            ogrenci_id__in=ogr_ids,
        ).values_list("ogrenci_id", flat=True)
    )


def _kapsam_disi_ids():
    """Bu app'in (Öğrenci Ders Planlaması) artık ilgilenmediği öğrenci pk seti.

    En son UYGULANMIŞ sene sonu geçişinde gerçekten terfi eden (durum="normal",
    yani Seviye+1 olan — sınıf tekrarı hariç, onların sınıfı değişmedi) öğrenciler
    ile o geçişten SONRA eklenmiş 9. sınıf yeni kayıt öğrencileri: ikisinin de
    gelecek yıl zorunlu/seçmeli ders seçimi zaten (geçen yılki döngüde ya da başka
    bir süreçle) tamamlanmış/tamamlanacak — bu app yalnızca hâlâ o geçişe dahil
    olmamış (örn. yıl içinde nakille gelen, sınıf tekrarı yapan ya da "inceleme
    gerekli" olarak bekleyen) öğrencilerle ilgilenmeye devam eder.
    """
    from senesonu.models import SeneSonuGecisi

    son_gecis = SeneSonuGecisi.objects.filter(uygulandi=True).order_by("-uygulama_zamani").first()
    if not son_gecis:
        return set()

    gecis_ids = set(son_gecis.ogrenci_gecisleri.values_list("ogrenci_id", flat=True))
    terfi_ids = set(
        son_gecis.ogrenci_gecisleri.filter(durum="normal").values_list("ogrenci_id", flat=True)
    )
    yeni_kayit_9_ids = set(
        Ogrenci.objects.filter(aktif=True, sinif=9)
        .exclude(pk__in=gecis_ids)
        .values_list("pk", flat=True)
    )
    return terfi_ids | yeni_kayit_9_ids


def _kapsam_kontrol(request, ogrenci):
    """Kapsam dışı bir öğrenciyse listeye yönlendiren mesajlı bir response döner, aksi halde None."""
    if ogrenci.pk in _kapsam_disi_ids():
        messages.warning(
            request,
            f"{ogrenci.adi} {ogrenci.soyadi} artık bu ekranın kapsamı dışında "
            "(sınıfı zaten terfi etti ya da yeni kayıt 9. sınıf öğrencisi).",
        )
        return redirect("ogrdrs_listesi")
    return None


def _seviyelere_grupla(ogr_listesi):
    """ogr_listesi'ni (her biri {'ogrenci': Ogrenci, ...} sözlüğü) sinif→şube gruplu
    `seviyeler` yapısına çevirir — ogrenci_listesi şablonunun beklediği format."""
    from collections import defaultdict

    seviye_sube_map = defaultdict(lambda: defaultdict(list))
    for ogr in ogr_listesi:
        seviye_sube_map[ogr["ogrenci"].sinif][ogr["ogrenci"].sube].append(ogr)

    seviyeler = []
    for sinif_no in sorted(seviye_sube_map):
        subeler = []
        for sube_harf in sorted(seviye_sube_map[sinif_no]):
            ogrenciler = seviye_sube_map[sinif_no][sube_harf]
            tamamladi = sum(
                1 for o in ogrenciler
                if not o["son_sinif"] and o["secmeli_maks"] > 0
                and o["secmeli_saat"] >= o["secmeli_maks"]
            )
            subeler.append({
                "sube": sube_harf,
                "sinif_sube": f"{sinif_no}/{sube_harf}",
                "ogrenciler": ogrenciler,
                "toplam": len(ogrenciler),
                "tamamladi": tamamladi,
            })
        seviyeler.append({
            "sinif_no": sinif_no,
            "subeler": subeler,
            "toplam_ogr": sum(len(s["ogrenciler"]) for s in subeler),
        })
    return seviyeler


def _gecmis_yil_ogr_listesi(secili_yil, sinif_filtre, sube_filtre):
    """`secili_yil`den başlayan UYGULANMIŞ sene sonu geçişindeki öğrencileri, O YILKİ
    (eski_sinif/eski_sube) hâlleriyle ve o yılın zorunlu/seçmeli ders atamalarıyla
    (egitim_yili=secili_yil) yeniden kurar. Salt okunur denetim amaçlıdır — hiçbir kayıt
    değiştirmez. Geçiş bulunamazsa (None, []) döner.

    Not: `Ogrenci.sinif`/`sube` geçiş sonrası GÜNCEL (terfi sonrası) değeri taşıdığından,
    döndürülen sözlüklerdeki `ogrenci` nesnelerinin sinif/sube alanları -- kaydedilmeden,
    yalnızca bu render için -- geçmiş değerlerle bellekte geçici olarak değiştirilir
    (bkz. secmelidersler.services.ders_dagilimi.plan_sinif_dagilimi_gecmis — aynı desen).
    """
    from senesonu.models import SeneSonuGecisi

    gecis = (
        SeneSonuGecisi.objects.filter(eski_egitim_yili=secili_yil, uygulandi=True)
        .order_by("-uygulama_zamani")
        .first()
    )
    if not gecis:
        return None, []

    satirlar = list(
        gecis.ogrenci_gecisleri.select_related("ogrenci")
        .order_by("eski_sinif", "eski_sube", "ogrenci__okulno")
    )
    if sinif_filtre:
        try:
            satirlar = [s for s in satirlar if s.eski_sinif == int(sinif_filtre)]
        except ValueError:
            pass
    if sube_filtre:
        satirlar = [s for s in satirlar if s.eski_sube.upper() == sube_filtre.upper()]

    ogr_ids = [s.ogrenci_id for s in satirlar]

    secmeli_map = {
        (row["ogrenci_id"], row["ders__grup__sinif_seviyesi"]): row["toplam"]
        for row in OgrenciSecmeliDers.objects.filter(
            ogrenci_id__in=ogr_ids, ders__grup__egitim_yili=secili_yil
        ).values("ogrenci_id", "ders__grup__sinif_seviyesi").annotate(toplam=Sum("secilen_saat"))
    }
    zorunlu_map = {
        row["ogrenci_id"]: row["sayi"]
        for row in OgrenciZorunluDers.objects.filter(
            ogrenci_id__in=ogr_ids, ortak_ders__egitim_yili=secili_yil
        ).values("ogrenci_id").annotate(sayi=Count("pk"))
    }

    _toplam_map = get_toplam_saat_map(secili_yil)
    secmeli_maks_map = {
        row["sinif_seviyesi"]: _toplam_map.get(row["sinif_seviyesi"], _VARSAYILAN_TOPLAM_SAAT) - (row["zorunlu"] or 0)
        for row in _yf(OrtakDers.objects, secili_yil).values("sinif_seviyesi").annotate(
            zorunlu=Sum("haftalik_saat")
        )
    }

    # Alan eşleşmesi (yalnızca bilgi amaçlı, buton yok — salt okunur ekranda gösterilir)
    alan_map = {}
    for lvl in (11, 12):
        alan_map[lvl] = list(Alan.objects.filter(sinif_seviyesi=lvl, egitim_yili=secili_yil).order_by("sira"))
    alan_ders_set_map = {
        alan.pk: set(AlanDers.objects.filter(alan=alan).values_list("ders_id", flat=True))
        for lvl_alanlar in alan_map.values() for alan in lvl_alanlar
    }
    ogr_ders_set_map = {}
    for row in OgrenciSecmeliDers.objects.filter(
        ogrenci_id__in=ogr_ids, ders__grup__sinif_seviyesi__in=(11, 12), ders__grup__egitim_yili=secili_yil
    ).values_list("ogrenci_id", "ders__grup__sinif_seviyesi", "ders_id"):
        ogr_id, lvl, ders_id = row
        ogr_ders_set_map.setdefault((ogr_id, lvl), set()).add(ders_id)

    ogr_listesi = []
    for satir in satirlar:
        o = satir.ogrenci
        o.sinif = satir.eski_sinif
        o.sube = satir.eski_sube

        mezun = satir.durum == "mezun"
        hedef_sinif = satir.yeni_sinif or satir.eski_sinif
        secmeli_maks = secmeli_maks_map.get(hedef_sinif, 0)

        alan_secenekleri = alan_map.get(hedef_sinif, [])
        secili_alan_ad = None
        if alan_secenekleri:
            ogr_ders_seti = ogr_ders_set_map.get((o.pk, hedef_sinif), set())
            for alan in alan_secenekleri:
                alan_ders_seti = alan_ders_set_map.get(alan.pk, set())
                if alan_ders_seti and ogr_ders_seti == alan_ders_seti:
                    secili_alan_ad = alan.adi
                    break

        ogr_listesi.append({
            "ogrenci": o,
            "gelecek_sinif": hedef_sinif,
            "son_sinif": mezun,
            "durum": satir.get_durum_display(),
            "tasdikname": False,
            "sinif_tekrari": satir.durum == "sinif_tekrari",
            "secmeli_saat": secmeli_map.get((o.pk, hedef_sinif), 0),
            "secmeli_maks": secmeli_maks,
            "zorunlu_sayi": zorunlu_map.get(o.pk, 0),
            "alan_secenekleri": [],
            "secili_alan_id": None,
            "secili_alan_ad": secili_alan_ad,
        })

    return gecis, ogr_listesi


@mudur_yardimcisi_required
def ogrenci_listesi(request):
    sinif_filtre = request.GET.get("sinif", "").strip()
    sube_filtre = request.GET.get("sube", "").strip()

    _aktif_yil = get_aktif_egitim_yili()
    secili_yil = _secili_yil(request, _aktif_yil)
    gecmis_mod = secili_yil != _aktif_yil
    # Dropdown'dan AKTİF yıl AÇIKÇA seçilmişse (yil param verilmiş, aktif yıla eşit)
    # kullanıcı geçmiş bir yıl seçtiğinde olduğu gibi TÜM sınıf/şube kapsamını görmek
    # ister; bu durumda "kapsam dışı" (zaten terfi etmiş/yeni kayıt) filtresi devre dışı
    # bırakılır — aksi hâlde dropdown'daki aktif yıl seçeneği hiçbir şeyi değiştirmez,
    # sayfa hep varsayılan (yalnızca istisnai öğrenciler) görünümüne düşer (bkz. commit
    # geçmişi: "?yil=<aktif yıl>" sayfası aktif yılın sınıf/şube bilgisinden habersiz
    # görünüyordu).
    yil_param_verildi = bool(request.GET.get("yil", "").strip())

    if gecmis_mod:
        gecis, ogr_listesi = _gecmis_yil_ogr_listesi(secili_yil, sinif_filtre, sube_filtre)
        seviyeler = _seviyelere_grupla(ogr_listesi)
        return render(request, "ogrencidersleri/ogrenci_listesi.html", {
            "title": "Öğrenci Ders Planlaması",
            "ogr_listesi": ogr_listesi,
            "seviyeler": seviyeler,
            "secilen_sinif": sinif_filtre,
            "secilen_sube": sube_filtre,
            "aktif_yil": _aktif_yil,
            "secili_yil": secili_yil,
            "secilebilir_yillar": _secilebilir_yillar(_aktif_yil),
            "salt_okunur": True,
            "gecis_yok": gecis is None,
        })

    _kapsam_disi = set() if yil_param_verildi else _kapsam_disi_ids()
    qs = Ogrenci.objects.filter(aktif=True).exclude(pk__in=_kapsam_disi).order_by("sinif", "sube", "okulno")
    if sinif_filtre:
        try:
            qs = qs.filter(sinif=int(sinif_filtre))
        except ValueError:
            pass
    if sube_filtre:
        qs = qs.filter(sube__iexact=sube_filtre)

    secmeli_map = {
        (row["ogrenci_id"], row["ders__grup__sinif_seviyesi"]): row["toplam"]
        for row in _yf(OgrenciSecmeliDers.objects, _aktif_yil, "ders__grup__egitim_yili").values(
            "ogrenci_id", "ders__grup__sinif_seviyesi"
        ).annotate(toplam=Sum("secilen_saat"))
    }
    zorunlu_map = {
        (row["ogrenci_id"], row["ortak_ders__sinif_seviyesi"]): row["sayi"]
        for row in _yf(OgrenciZorunluDers.objects, _aktif_yil, "ortak_ders__egitim_yili").values(
            "ogrenci_id", "ortak_ders__sinif_seviyesi"
        ).annotate(sayi=Count("pk"))
    }

    # Gelecek sınıf seviyesi → maks seçmeli saat (toplam - zorunlu)
    _toplam_map = get_toplam_saat_map(_aktif_yil)
    secmeli_maks_map = {
        row["sinif_seviyesi"]: _toplam_map.get(row["sinif_seviyesi"], _VARSAYILAN_TOPLAM_SAAT) - (row["zorunlu"] or 0)
        for row in _yf(OrtakDers.objects, _aktif_yil).values("sinif_seviyesi").annotate(
            zorunlu=Sum("haftalik_saat")
        )
    }

    tum_siniflar = list(
        Ogrenci.objects.filter(aktif=True).exclude(pk__in=_kapsam_disi)
        .values_list("sinif", flat=True).distinct().order_by("sinif")
    )
    tum_subeler = list(
        Ogrenci.objects.filter(aktif=True).exclude(pk__in=_kapsam_disi)
        .values_list("sube", flat=True).distinct().order_by("sube")
    )

    tum_ogr_ids = list(qs.values_list("pk", flat=True))
    _tekrari_ids   = _sinif_tekrari_ids(tum_ogr_ids, _aktif_yil)
    _tasdikname_ids_set = _tasdikname_ids(tum_ogr_ids)

    # Alan (TM/MF/DİL vb.) seçenekleri yalnızca 11-12. sınıf seviyeleri için tanımlanır.
    alan_map = {}
    for lvl in (11, 12):
        alan_map[lvl] = list(
            _yf(Alan.objects.filter(sinif_seviyesi=lvl), _aktif_yil).order_by("sira")
        )

    # Her alanın ders id kümesi (öğrencinin mevcut seçimiyle tam eşleşme kontrolü için)
    alan_ders_set_map = {
        alan.pk: set(
            AlanDers.objects.filter(alan=alan).values_list("ders_id", flat=True)
        )
        for lvl_alanlar in alan_map.values() for alan in lvl_alanlar
    }

    # Öğrencinin (gelecek sınıf seviyesindeki) mevcut seçmeli ders id kümesi
    ogr_ders_set_map = {}
    for row in OgrenciSecmeliDers.objects.filter(
        ogrenci_id__in=tum_ogr_ids, ders__grup__sinif_seviyesi__in=(11, 12)
    ).values_list("ogrenci_id", "ders__grup__sinif_seviyesi", "ders_id"):
        ogr_id, lvl, ders_id = row
        ogr_ders_set_map.setdefault((ogr_id, lvl), set()).add(ders_id)

    ogr_listesi = []
    for o in qs:
        tekrari    = o.pk in _tekrari_ids
        tasdikname = o.pk in _tasdikname_ids_set
        gelecek = o.sinif if tekrari else _GELECEK(o.sinif)
        secmeli_maks = secmeli_maks_map.get(gelecek, 0)

        alan_secenekleri = alan_map.get(gelecek, [])
        secili_alan_id = None
        if alan_secenekleri:
            ogr_ders_seti = ogr_ders_set_map.get((o.pk, gelecek), set())
            for alan in alan_secenekleri:
                alan_ders_seti = alan_ders_set_map.get(alan.pk, set())
                if alan_ders_seti and ogr_ders_seti == alan_ders_seti:
                    secili_alan_id = alan.pk
                    break

        ogr_listesi.append({
            "ogrenci": o,
            "gelecek_sinif": gelecek,
            "son_sinif": gelecek > 12,
            "tasdikname": tasdikname,
            "sinif_tekrari": tekrari,
            "secmeli_saat": secmeli_map.get((o.pk, gelecek), 0),
            "secmeli_maks": secmeli_maks,
            "zorunlu_sayi": zorunlu_map.get((o.pk, gelecek), 0),
            "alan_secenekleri": alan_secenekleri,
            "secili_alan_id": secili_alan_id,
        })

    seviyeler = _seviyelere_grupla(ogr_listesi)

    return render(request, "ogrencidersleri/ogrenci_listesi.html", {
        "title": "Öğrenci Ders Planlaması",
        "ogr_listesi": ogr_listesi,
        "seviyeler": seviyeler,
        "tum_siniflar": tum_siniflar,
        "tum_subeler": tum_subeler,
        "secilen_sinif": sinif_filtre,
        "secilen_sube": sube_filtre,
        "aktif_yil": _aktif_yil,
        "secili_yil": secili_yil,
        "secilebilir_yillar": _secilebilir_yillar(_aktif_yil),
        "salt_okunur": False,
    })


@mudur_yardimcisi_required
def ogrenci_alan_ata(request, ogrenci_pk, alan_pk):
    """Öğrencinin seçmeli ders seçimini seçilen Alan'ın (TM/MF/DİL vb.) ders paketiyle değiştirir."""
    if request.method != "POST":
        return redirect("ogrdrs_listesi")

    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)
    engel = _kapsam_kontrol(request, ogrenci)
    if engel:
        return engel
    alan = get_object_or_404(Alan, pk=alan_pk)

    alan_dersler = list(AlanDers.objects.filter(alan=alan).select_related("ders"))
    if not alan_dersler:
        messages.error(request, f"{alan.adi} alanı için tanımlı ders bulunmuyor.")
    else:
        from secmelidersler.services.secim_sayisi import secim_sayisi_asim_uyarilari
        secimler = [(ad.ders, ad.secilen_saat) for ad in alan_dersler]
        uyarilar = secim_sayisi_asim_uyarilari(ogrenci, secimler, haric_egitim_yili=alan.egitim_yili)

        OgrenciSecmeliDers.objects.filter(
            ogrenci=ogrenci,
            ders__grup__sinif_seviyesi=alan.sinif_seviyesi,
            ders__grup__egitim_yili=alan.egitim_yili,
        ).delete()
        OgrenciSecmeliDers.objects.bulk_create([
            OgrenciSecmeliDers(ogrenci=ogrenci, ders=ad.ders, secilen_saat=ad.secilen_saat)
            for ad in alan_dersler
        ])
        if ogrenci.sinif == alan.sinif_seviyesi:
            ogrenci.sectigi_alan = alan.adi
            ogrenci.save(update_fields=["sectigi_alan"])
        messages.success(
            request,
            f"{ogrenci.adi} {ogrenci.soyadi} — seçmeli ders seçimi {alan.adi} alanına göre tamamlandı.",
        )
        for uyari in uyarilar:
            messages.warning(request, uyari)

    sinif = request.POST.get("sinif", "").strip()
    sube = request.POST.get("sube", "").strip()
    url = reverse("ogrdrs_listesi")
    if sinif:
        url += f"?sinif={sinif}&sube={sube}&ogr={ogrenci_pk}#ogr-tablo"
    return redirect(url)


@mudur_yardimcisi_required
def ogrenci_detay(request, ogrenci_pk):
    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)
    engel = _kapsam_kontrol(request, ogrenci)
    if engel:
        return engel
    tasdikname_var = OgrenciTasdikname.objects.filter(ogrenci=ogrenci).exists()
    # --- Sonraki Yıl ---
    aktif_yil = get_aktif_egitim_yili()
    sinif_tekrari_qs = OgrenciSinifTekrari.objects.filter(ogrenci=ogrenci)
    if aktif_yil:
        sinif_tekrari_qs = sinif_tekrari_qs.filter(egitim_yili=aktif_yil)
    sinif_tekrari = sinif_tekrari_qs.exists()
    gelecek_sinif = ogrenci.sinif if sinif_tekrari else _GELECEK(ogrenci.sinif)

    if gelecek_sinif > 12:
        return render(request, "ogrencidersleri/son_sinif.html", {
            "title": "Öğrenci Ders Planlaması",
            "ogrenci": ogrenci,
        })

    zorunlu_atamalar_qs = OgrenciZorunluDers.objects.filter(
        ogrenci=ogrenci, ortak_ders__sinif_seviyesi=gelecek_sinif
    )
    if aktif_yil:
        zorunlu_atamalar_qs = zorunlu_atamalar_qs.filter(ortak_ders__egitim_yili=aktif_yil)
    zorunlu_atamalar = (
        zorunlu_atamalar_qs
        .select_related("ortak_ders")
        .order_by("ortak_ders__sira")
    )
    ortak_ders_havuz = _yf(
        OrtakDers.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil
    ).order_by("sira")
    atanmis_ids = {a.ortak_ders_id for a in zorunlu_atamalar}
    zorunlu_toplam_saat = sum(a.ortak_ders.haftalik_saat for a in zorunlu_atamalar)

    secmeli_secimler_qs = OgrenciSecmeliDers.objects.filter(
        ogrenci=ogrenci, ders__grup__sinif_seviyesi=gelecek_sinif
    )
    if aktif_yil:
        secmeli_secimler_qs = secmeli_secimler_qs.filter(ders__grup__egitim_yili=aktif_yil)
    secmeli_secimler = (
        secmeli_secimler_qs
        .select_related("ders__grup")
        .order_by("ders__grup__sira", "ders__sira")
    )
    secmeli_toplam_saat = sum(s.secilen_saat for s in secmeli_secimler)

    ortak_toplam = ortak_ders_havuz.aggregate(
        t=Coalesce(Sum("haftalik_saat"), Value(0))
    )["t"]
    secmeli_maks_saat = get_toplam_saat(gelecek_sinif, egitim_yili=aktif_yil) - ortak_toplam

    return render(request, "ogrencidersleri/ogrenci_detay.html", {
        "title": f"Ders Planı — {ogrenci.adi} {ogrenci.soyadi}",
        "ogrenci": ogrenci,
        "gelecek_sinif": gelecek_sinif,
        "tasdikname_var": tasdikname_var,
        "sinif_tekrari": sinif_tekrari,
        # Sonraki yıl
        "zorunlu_atamalar": zorunlu_atamalar,
        "ortak_ders_havuz": ortak_ders_havuz,
        "atanmis_ids": atanmis_ids,
        "zorunlu_toplam_saat": zorunlu_toplam_saat,
        "secmeli_secimler": secmeli_secimler,
        "secmeli_toplam_saat": secmeli_toplam_saat,
        "secmeli_maks_saat": secmeli_maks_saat,
        "tum_zorunlu_atandi": len(atanmis_ids) == ortak_ders_havuz.count(),
    })


@mudur_yardimcisi_required
def sinif_toplu_zorunlu_ata(request):
    """POST: Bir sınıf/şubedeki tüm öğrencilere gelecek yıl zorunlu derslerini toplu atar."""
    if request.method != "POST":
        return redirect("ogrdrs_listesi")

    sinif_str = request.POST.get("sinif", "").strip()
    sube = request.POST.get("sube", "").strip().upper()

    try:
        sinif = int(sinif_str)
    except (ValueError, TypeError):
        messages.error(request, "Geçersiz sınıf değeri.")
        return redirect("ogrdrs_listesi")

    return _toplu_zorunlu_ata_impl(request, sinif, sube, _GELECEK(sinif), kendi_seviyesi=False)


@mudur_yardimcisi_required
def sube_zorunlu_ata_mevcut(request):
    """POST: Bir sınıf/şubedeki tüm öğrencilere KENDİ sınıf seviyesindeki zorunlu dersleri toplu atar."""
    if request.method != "POST":
        return redirect("ogrdrs_listesi")

    sinif_str = request.POST.get("sinif", "").strip()
    sube = request.POST.get("sube", "").strip().upper()

    try:
        sinif = int(sinif_str)
    except (ValueError, TypeError):
        messages.error(request, "Geçersiz sınıf değeri.")
        return redirect("ogrdrs_listesi")

    return _toplu_zorunlu_ata_impl(request, sinif, sube, sinif, kendi_seviyesi=True)


def _toplu_zorunlu_ata_impl(request, sinif, sube, hedef_sinif, kendi_seviyesi):
    varsayilan_yonlendir = f"{reverse('ogrdrs_listesi')}?sinif={sinif}&sube={sube}#ogr-tablo"
    yonlendir = request.POST.get("next") or varsayilan_yonlendir

    if hedef_sinif > 12:
        messages.warning(request, f"{sinif}/{sube} öğrencileri son sınıf — zorunlu ders ataması yapılamaz.")
        return redirect(yonlendir)

    aktif_yil = get_aktif_egitim_yili()
    zorunlu_dersler = list(_yf(OrtakDers.objects.filter(sinif_seviyesi=hedef_sinif), aktif_yil))

    if not zorunlu_dersler:
        messages.warning(request, f"{hedef_sinif}. sınıf için aktif yılda zorunlu ders tanımlanmamış.")
        return redirect(yonlendir)

    # "Kendi seviyesi" (mevcut) ataması — örn. yeni kayıt 9. sınıf öğrencilerine kendi
    # sınıf seviyelerinin derslerini atamak için `ogrenci:yeni_kayit_hub`dan çağrılır —
    # `_kapsam_disi_ids()` uygulanmaz: bu öğrenciler zaten TAM OLARAK o kümenin içindeki
    # "yeni kayıt 9. sınıf" öğrencileridir (bkz. commit geçmişi — filtre uygulanınca bu
    # buton onlar için hiçbir şey yapmıyordu). Bunun yerine sınıf tekrarı yapan
    # öğrenciler dışlanır — onlar "yeni kayıt" değil, devam eden bir kayıttır; kendi
    # ders ataması `secmeli:sinif_tekrari_listesi` / `secmeli:sinif_dagilimi`
    # akışlarından yürütülür. "Gelecek sınıf" ataması (kendi_seviyesi=False) için
    # filtre eskisi gibi uygulanır — bu app'in normal çalışma kapsamı odur.
    aday_ids = list(
        Ogrenci.objects.filter(sinif=sinif, sube=sube, aktif=True).values_list("pk", flat=True)
    )
    if kendi_seviyesi:
        _disi = _sinif_tekrari_ids(aday_ids, aktif_yil)
    else:
        _disi = _kapsam_disi_ids()
    ogrenciler = list(
        Ogrenci.objects.filter(pk__in=aday_ids).exclude(pk__in=_disi)
    )
    if not ogrenciler:
        messages.warning(request, f"{sinif}/{sube} şubesinde işlem kapsamında öğrenci bulunamadı.")
        return redirect(yonlendir)

    yeni_atamalar = [
        OgrenciZorunluDers(ogrenci=ogr, ortak_ders=ders)
        for ogr in ogrenciler
        for ders in zorunlu_dersler
    ]
    OgrenciZorunluDers.objects.bulk_create(yeni_atamalar, ignore_conflicts=True)

    messages.success(
        request,
        f"{sinif}/{sube} — {len(ogrenciler)} öğrenciye {hedef_sinif}. sınıf "
        f"{len(zorunlu_dersler)} zorunlu ders atandı."
    )
    return redirect(yonlendir)


@mudur_yardimcisi_required
def sube_secmeli_form(request, sinif, sube):
    """
    Bir sınıf/şubedeki tüm öğrenciler için gelecek sınıf seviyesinde okutulacak
    seçmeli ders paketini seçip tek seferde tüm şubeye atamayı sağlar.
    """
    return _sube_secmeli_form_impl(request, sinif, sube, _GELECEK(sinif), kendi_seviyesi=False)


@mudur_yardimcisi_required
def sube_secmeli_form_mevcut(request, sinif, sube):
    """
    Bir sınıf/şubedeki tüm öğrenciler için KENDİ sınıf seviyesinde okutulacak
    seçmeli ders paketini seçip tek seferde tüm şubeye atamayı sağlar (örn. yeni
    kayıt olan öğrencilere kendi sınıf seviyelerinin seçmeli derslerini atamak için).
    """
    return _sube_secmeli_form_impl(request, sinif, sube, sinif, kendi_seviyesi=True)


def _sube_secmeli_form_impl(request, sinif, sube, hedef_sinif, kendi_seviyesi):
    sube = sube.upper()
    varsayilan_yonlendir = f"{reverse('ogrdrs_listesi')}?sinif={sinif}&sube={sube}#ogr-tablo"
    yonlendir = request.POST.get("next") or varsayilan_yonlendir
    aktif_yil = get_aktif_egitim_yili()

    # bkz. _toplu_zorunlu_ata_impl'deki aynı isimli not — "kendi seviyesi" ataması
    # (örn. yeni kayıt 9. sınıf) `_kapsam_disi_ids()` yerine sınıf tekrarı yapan
    # öğrencileri dışlar; onlar "yeni kayıt" değildir.
    aday_ids = list(
        Ogrenci.objects.filter(sinif=sinif, sube=sube, aktif=True).values_list("pk", flat=True)
    )
    _disi = _sinif_tekrari_ids(aday_ids, aktif_yil) if kendi_seviyesi else _kapsam_disi_ids()
    ogrenciler = list(
        Ogrenci.objects.filter(pk__in=aday_ids).exclude(pk__in=_disi)
    )
    if not ogrenciler:
        messages.warning(request, f"{sinif}/{sube} şubesinde işlem kapsamında öğrenci bulunamadı.")
        return redirect(yonlendir)

    if hedef_sinif > 12:
        messages.warning(request, f"{sinif}/{sube} öğrencileri son sınıf — seçmeli ders ataması yapılamaz.")
        return redirect(yonlendir)

    if not _yf(SecmeliDersGrubu.objects.filter(sinif_seviyesi=hedef_sinif), aktif_yil).exists():
        messages.warning(request, f"{hedef_sinif}. sınıf için seçmeli ders grubu tanımlanmamış.")
        return redirect(yonlendir)

    if request.method == "POST":
        form = OgrenciSecmeliDersForm(hedef_sinif, ogrenci=None, egitim_yili=aktif_yil, data=request.POST)
        if form.is_valid():
            secimler = form.get_secimler()

            # Bir dersin öğrenci başına en fazla kaç kez seçilebileceği (bkz.
            # SecmeliDersHavuzu.secimsayisi) — engelleyici değil, bilgilendirici;
            # toplu atamada HER öğrenci için ayrı ayrı kontrol edilir (form burada
            # tek bir öğrenciye bağlı olmadığından `OgrenciSecmeliDersForm.clean()`
            # bunu kendi başına yapamaz).
            from secmelidersler.services.secim_sayisi import secim_sayisi_asim_uyarilari
            tum_uyarilar = []
            for ogr in ogrenciler:
                tum_uyarilar.extend(
                    secim_sayisi_asim_uyarilari(ogr, secimler, haric_egitim_yili=aktif_yil)
                )

            eski_qs = OgrenciSecmeliDers.objects.filter(
                ogrenci__in=ogrenciler, ders__grup__sinif_seviyesi=hedef_sinif
            )
            if aktif_yil:
                eski_qs = eski_qs.filter(ders__grup__egitim_yili=aktif_yil)
            eski_qs.delete()
            yeni_atamalar = [
                OgrenciSecmeliDers(ogrenci=ogr, ders=ders, secilen_saat=saat)
                for ogr in ogrenciler
                for ders, saat in secimler
            ]
            OgrenciSecmeliDers.objects.bulk_create(yeni_atamalar)
            messages.success(
                request,
                f"{sinif}/{sube} — {len(ogrenciler)} öğrenciye {hedef_sinif}. sınıf "
                f"seçmeli ders paketi ({len(secimler)} ders) atandı.",
            )
            for uyari in tum_uyarilar[:20]:
                messages.warning(request, uyari)
            if len(tum_uyarilar) > 20:
                messages.warning(request, f"...ve {len(tum_uyarilar) - 20} uyarı daha.")
            return redirect(yonlendir)
    else:
        form = OgrenciSecmeliDersForm(hedef_sinif, ogrenci=None, egitim_yili=aktif_yil)

    ortak_dersler = _yf(
        OrtakDers.objects.filter(sinif_seviyesi=hedef_sinif), aktif_yil
    ).order_by("sira")
    ortak_toplam_saat = ortak_dersler.aggregate(
        toplam=Coalesce(Sum("haftalik_saat"), Value(0))
    )["toplam"]

    grup_listesi = [
        {
            "grup": grup,
            "fields": [
                {
                    "field": form[fname],
                    "saat_field": form[fname_saat] if fname_saat else None,
                    "ders": ders,
                }
                for fname, fname_saat, ders in field_items
            ],
        }
        for grup, field_items in form.grup_field_map.values()
    ]

    alanlar = _yf(Alan.objects.filter(sinif_seviyesi=hedef_sinif), aktif_yil).order_by("sira")
    alan_verileri = []
    for alan in alanlar:
        ders_saat = {
            ad.ders_id: ad.secilen_saat
            for ad in AlanDers.objects.filter(alan=alan)
        }
        alan_verileri.append({"id": alan.pk, "adi": alan.adi, "ders_saat": ders_saat})

    return render(request, "ogrencidersleri/sube_secmeli_form.html", {
        "title": f"{hedef_sinif}. Sınıf Seçmeli Ders — {sinif}/{sube} Şubesi",
        "sinif": sinif,
        "sube": sube,
        "ogrenci_sayisi": len(ogrenciler),
        "mevcut_sinif": sinif,
        "gelecek_sinif": hedef_sinif,
        "kendi_seviyesi": kendi_seviyesi,
        "next": request.GET.get("next", ""),
        "form": form,
        "grup_listesi": grup_listesi,
        "ortak_dersler": ortak_dersler,
        "ortak_toplam_saat": ortak_toplam_saat,
        "maks_saat": form.MAKS_SAAT,
        "toplam_saat": get_toplam_saat(hedef_sinif),
        "alan_verileri": alan_verileri,
    })


@mudur_yardimcisi_required
def ogrenci_zorunlu_ata(request, ogrenci_pk):
    """POST: Öğrencinin gelecek sınıf seviyesindeki tüm zorunlu dersleri atar."""
    if request.method != "POST":
        return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)

    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)
    engel = _kapsam_kontrol(request, ogrenci)
    if engel:
        return engel
    aktif_yil = get_aktif_egitim_yili()
    sinif_tekrari_qs = OgrenciSinifTekrari.objects.filter(ogrenci=ogrenci)
    if aktif_yil:
        sinif_tekrari_qs = sinif_tekrari_qs.filter(egitim_yili=aktif_yil)
    sinif_tekrari = sinif_tekrari_qs.exists()
    gelecek_sinif = ogrenci.sinif if sinif_tekrari else _GELECEK(ogrenci.sinif)

    ortak_dersler = _yf(OrtakDers.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil)
    eklenen = 0
    for ders in ortak_dersler:
        _, created = OgrenciZorunluDers.objects.get_or_create(
            ogrenci=ogrenci, ortak_ders=ders
        )
        if created:
            eklenen += 1

    if eklenen:
        messages.success(request, f"{eklenen} zorunlu ders atandı.")
    else:
        messages.info(request, "Tüm zorunlu dersler zaten atanmış.")

    return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)


@mudur_yardimcisi_required
def ogrenci_zorunlu_sil(request, ogrenci_pk, ders_pk):
    """POST: Öğrencinin bir zorunlu ders atamasını kaldırır."""
    if request.method != "POST":
        return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)

    atama = get_object_or_404(OgrenciZorunluDers, ogrenci_id=ogrenci_pk, ortak_ders_id=ders_pk)
    ders_adi = atama.ortak_ders.ders_adi
    atama.delete()
    messages.success(request, f"'{ders_adi}' ataması kaldırıldı.")
    return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)


def _ogrenci_secmeli_form_render(
    request, ogrenci, sinif_seviyesi, egitim_yili, geri_url, pdf_url=None,
    secili_alan_pk=None, basari_redirect=None,
):
    """`sinif_seviyesi`/`egitim_yili` için öğrencinin seçmeli ders seçim formunu
    render eder ve POST'ta kaydeder. Hem `ogrenci_secmeli_form` (ileri dönük
    planlama — hedef seviye `_GELECEK`/sınıf tekrarından hesaplanır) hem de
    `ogrenci_secmeli_form_seviye` (Sınıf Dağılımı denetim ekranından — hedef
    seviye doğrudan parametredir) bu ortak gövdeyi kullanır; tek kaynak
    `OgrenciSecmeliDersForm` + `ogrenci_secmeli_form.html`.
    """
    ortak_dersler = _yf(
        OrtakDers.objects.filter(sinif_seviyesi=sinif_seviyesi), egitim_yili
    ).order_by("sira")
    ortak_toplam_saat = ortak_dersler.aggregate(
        toplam=Coalesce(Sum("haftalik_saat"), Value(0))
    )["toplam"]
    gruplar_var = _yf(
        SecmeliDersGrubu.objects.filter(sinif_seviyesi=sinif_seviyesi), egitim_yili
    ).exists()

    if not gruplar_var:
        return render(request, "ogrencidersleri/yapilandirilmamis.html", {
            "title": "Seçmeli Ders Seçimi",
            "ogrenci": ogrenci,
            "sinif_seviyesi": sinif_seviyesi,
        })

    if request.method == "POST":
        form = OgrenciSecmeliDersForm(sinif_seviyesi, ogrenci=ogrenci, egitim_yili=egitim_yili, data=request.POST)
        if form.is_valid():
            form.kaydet()
            messages.success(
                request,
                f"{ogrenci.adi} {ogrenci.soyadi} için {sinif_seviyesi}. sınıf seçmeli ders seçimi kaydedildi.",
            )
            for uyari in form.secim_sayisi_uyarilari:
                messages.warning(request, uyari)
            return redirect(basari_redirect or geri_url)
    else:
        form = OgrenciSecmeliDersForm(sinif_seviyesi, ogrenci=ogrenci, egitim_yili=egitim_yili)

    grup_listesi = [
        {
            "grup": grup,
            "fields": [
                {
                    "field": form[fname],
                    "saat_field": form[fname_saat] if fname_saat else None,
                    "ders": ders,
                }
                for fname, fname_saat, ders in field_items
            ],
        }
        for grup, field_items in form.grup_field_map.values()
    ]

    alanlar = _yf(Alan.objects.filter(sinif_seviyesi=sinif_seviyesi), egitim_yili).order_by("sira")
    alan_verileri = []
    for alan in alanlar:
        ders_saat = {
            ad.ders_id: ad.secilen_saat
            for ad in AlanDers.objects.filter(alan=alan)
        }
        alan_verileri.append({"id": alan.pk, "adi": alan.adi, "ders_saat": ders_saat})

    return render(request, "ogrencidersleri/ogrenci_secmeli_form.html", {
        "title": f"{sinif_seviyesi}. Sınıf Seçmeli Ders — {ogrenci.adi} {ogrenci.soyadi}",
        "ogrenci": ogrenci,
        "mevcut_sinif": ogrenci.sinif,
        "gelecek_sinif": sinif_seviyesi,
        "form": form,
        "grup_listesi": grup_listesi,
        "ortak_dersler": ortak_dersler,
        "ortak_toplam_saat": ortak_toplam_saat,
        "maks_saat": form.MAKS_SAAT,
        "toplam_saat": get_toplam_saat(sinif_seviyesi, egitim_yili=egitim_yili),
        "alan_verileri": alan_verileri,
        "geri_url": geri_url,
        "pdf_url": pdf_url,
        "secili_alan_pk": secili_alan_pk,
    })


@mudur_yardimcisi_required
def ogrenci_secmeli_form(request, ogrenci_pk):
    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)
    engel = _kapsam_kontrol(request, ogrenci)
    if engel:
        return engel
    aktif_yil = get_aktif_egitim_yili()

    # Tasdikname kontrolü — seçmeli ders seçiminden dışarıda
    if OgrenciTasdikname.objects.filter(ogrenci=ogrenci).exists():
        return render(request, "ogrencidersleri/tasdikname_engel.html", {
            "title": "Seçmeli Ders Seçimi",
            "ogrenci": ogrenci,
        })

    # Sınıf tekrarı kontrolü — aynı seviyede seçim yapar
    sinif_tekrari_qs = OgrenciSinifTekrari.objects.filter(ogrenci=ogrenci)
    if aktif_yil:
        sinif_tekrari_qs = sinif_tekrari_qs.filter(egitim_yili=aktif_yil)
    sinif_tekrari = sinif_tekrari_qs.exists()
    gelecek_sinif = ogrenci.sinif if sinif_tekrari else _GELECEK(ogrenci.sinif)

    if gelecek_sinif > 12:
        return render(request, "ogrencidersleri/son_sinif.html", {
            "title": "Seçmeli Ders Seçimi",
            "ogrenci": ogrenci,
        })

    return _ogrenci_secmeli_form_render(
        request, ogrenci, gelecek_sinif, aktif_yil,
        geri_url=reverse("ogrdrs_detay", args=[ogrenci.pk]),
        pdf_url=reverse("ogrdrs_secmeli_pdf", args=[ogrenci.pk]),
    )


@mudur_yardimcisi_required
def ogrenci_secmeli_form_seviye(request, ogrenci_pk, sinif_seviyesi):
    """Sınıf Dağılımı denetim ekranından (bkz. secmelidersler.views.sinif_dagilimi /
    plan_sinif_dagilimi_gecmis) tetiklenir: bir öğrencinin GÜNCEL `sinif_seviyesi`
    sindeki seçmeli ders seçimini düzenler. `ogrenci_secmeli_form`dan farkı: hedef
    seviye öğrencinin "gelecek sınıfı" (bkz. `_GELECEK`/sınıf tekrarı) yerine
    DOĞRUDAN URL parametresi olarak verilir — denetim ekranı zaten öğrencinin
    MEVCUT seviyesini konu eder, ileri dönük planlamayı değil. Bu yüzden
    `_kapsam_kontrol` de burada UYGULANMAZ: denetimdeki öğrenciler tipik olarak
    tam da bu app'in "gelecek yıl planlaması" ekranlarının artık ilgilenmediği
    (terfi etmiş) öğrencilerdir — bkz. `_kapsam_disi_ids`.
    """
    from okul.models import EgitimOgretimYili
    from secmelidersler.services.ders_dagilimi import baskin_egitim_yili

    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)

    yil_pk = request.GET.get("yil") or request.POST.get("yil", "")
    secili_yil = EgitimOgretimYili.objects.filter(pk=yil_pk).first() if yil_pk else None
    egitim_yili = baskin_egitim_yili(sinif_seviyesi, secili_yil or get_aktif_egitim_yili())

    geri_url = reverse("secmeli_sinif_dagilimi")
    if yil_pk:
        geri_url += f"?yil={yil_pk}"

    return _ogrenci_secmeli_form_render(
        request, ogrenci, sinif_seviyesi, egitim_yili,
        geri_url=geri_url,
        secili_alan_pk=request.GET.get("alan", "").strip() or None,
        basari_redirect=geri_url,
    )


@mudur_yardimcisi_required
def ogrenci_secmeli_pdf(request, ogrenci_pk):
    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)
    engel = _kapsam_kontrol(request, ogrenci)
    if engel:
        return engel
    aktif_yil = get_aktif_egitim_yili()
    sinif_tekrari_qs = OgrenciSinifTekrari.objects.filter(ogrenci=ogrenci)
    if aktif_yil:
        sinif_tekrari_qs = sinif_tekrari_qs.filter(egitim_yili=aktif_yil)
    sinif_tekrari = sinif_tekrari_qs.exists()
    gelecek_sinif = ogrenci.sinif if sinif_tekrari else _GELECEK(ogrenci.sinif)

    if gelecek_sinif > 12:
        return redirect("ogrdrs_secmeli_form", ogrenci_pk=ogrenci_pk)

    ortak_dersler = _yf(
        OrtakDers.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil
    ).order_by("sira")
    secmeli_gruplar = _yf(
        SecmeliDersGrubu.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil
    ).prefetch_related("dersler").order_by("sira")
    secimler = OgrenciSecmeliDers.objects.filter(
        ogrenci=ogrenci, ders__grup__sinif_seviyesi=gelecek_sinif
    )
    if aktif_yil:
        secimler = secimler.filter(ders__grup__egitim_yili=aktif_yil)
    secilen_ders_ids = {s.ders_id for s in secimler}
    secilen_saatler = {s.ders_id: s.secilen_saat for s in secimler}

    okul_bilgi = OkulBilgi.objects.first()
    egitim_yili = aktif_yil

    buf = BytesIO()
    secmeli_ders_pdf(
        buffer=buf,
        ogrenci=ogrenci,
        gelecek_sinif=gelecek_sinif,
        ortak_dersler=ortak_dersler,
        secmeli_gruplar=secmeli_gruplar,
        secilen_ders_ids=secilen_ders_ids,
        secilen_saatler=secilen_saatler,
        okul_bilgi=okul_bilgi,
        egitim_yili=egitim_yili,
        toplam_saat=get_toplam_saat(gelecek_sinif),
    )
    buf.seek(0)
    dosya_adi = f"secmeli_{ogrenci.okulno}_{gelecek_sinif}sinif.pdf"
    response = HttpResponse(buf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{dosya_adi}"'
    return response
