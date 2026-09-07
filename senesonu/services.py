"""Sene sonu öğrenci sınıf/şube atlatma iş mantığı.

`gecis_olustur` bir taslak (SeneSonuGecisi + satırları) oluşturur, henüz `ogrenci.Ogrenci`
kayıtlarına dokunmaz. `gecis_uygula` taslağı kalıcı hale getirir.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import SeneSonuGecisi, SeneSonuOgrenciGecisi


def _yeni_subeler_belirle(sinif_no, adet, egitim_yili):
    """`sinif_no` seviyesi için `adet` kadar şube harfi belirler.

    Önce o sınıf seviyesinde `egitim_yili` itibarıyla KAPALI şubeler (varsa, harf
    sırasına göre) yeniden kullanılır; kalan ihtiyaç için henüz hiç kullanılmayan
    (ne açık ne kapalı bir kaydı olan) sıradaki yeni harfler üretilir. Açık/kapalı
    durumu yıla göre değişebildiğinden (bkz. SinifSube.acik_mi — commit geçmişi) bu
    fonksiyon `egitim_yili`yi açıkça alır; şubelerin fiilen açılması/oluşturulması
    `gecis_uygula` içinde yapılır — bu fonksiyon yalnızca hangi harflerin
    kullanılacağını belirler.
    """
    from okul.models import SinifSube
    from secmelidersler.services.ders_dagilimi import HARFLER

    tum_subeler = list(SinifSube.objects.filter(sinif=sinif_no))
    kapali_harfler = sorted(ss.sube for ss in tum_subeler if not ss.acik_mi(egitim_yili))
    kullanimda = {ss.sube for ss in tum_subeler}

    secilen = kapali_harfler[:adet]
    for harf in HARFLER:
        if len(secilen) >= adet:
            break
        if harf not in kullanimda and harf not in secilen:
            secilen.append(harf)
    return secilen


def gecis_olustur(eski_yil, yeni_yil, kullanici=None):
    from ogrenci.models import Ogrenci
    from secmelidersler.models import OgrenciSinifTekrari
    from secmelidersler.services.ders_dagilimi import plan_sinif_dagilimi

    with transaction.atomic():
        gecis = SeneSonuGecisi.objects.create(
            eski_egitim_yili=eski_yil,
            yeni_egitim_yili=yeni_yil,
            olusturan=kullanici,
        )

        satirlar = []

        def _sinif_tekrari_ids(sinif_no):
            # `eski_yil`e göre kapsamlanır — aksi hâlde geçmiş bir yılda sınıfta
            # kalmış ama o yılı zaten tamamlayıp normal terfi eden bir öğrenci de
            # kalıcı olarak sınıf-tekrarı kabul edilip bu geçişte de yanlışlıkla
            # aynı seviyede tutulur (bkz. commit geçmişi).
            return set(
                OgrenciSinifTekrari.objects.filter(
                    ogrenci__aktif=True,
                    ogrenci__sinif=sinif_no,
                    egitim_yili=eski_yil,
                ).values_list("ogrenci_id", flat=True)
            )

        # 9 → 10 ve 11 → 12: şube aynı kalır.
        for eski_sinif, yeni_sinif in ((9, 10), (11, 12)):
            tekrar_ids = _sinif_tekrari_ids(eski_sinif)
            for ogr in Ogrenci.objects.filter(aktif=True, sinif=eski_sinif).order_by("okulno"):
                if ogr.pk in tekrar_ids:
                    satirlar.append(SeneSonuOgrenciGecisi(
                        gecis=gecis, ogrenci=ogr,
                        eski_sinif=eski_sinif, eski_sube=ogr.sube,
                        yeni_sinif=eski_sinif, yeni_sube=ogr.sube,
                        durum="sinif_tekrari",
                    ))
                else:
                    satirlar.append(SeneSonuOgrenciGecisi(
                        gecis=gecis, ogrenci=ogr,
                        eski_sinif=eski_sinif, eski_sube=ogr.sube,
                        yeni_sinif=yeni_sinif, yeni_sube=ogr.sube,
                        durum="normal",
                    ))

        # 10 → 11: alan bazlı hesaplanan şube. `_sube_dagit` harfleri sadece sıra/ordinal
        # olarak üretir (kapalı/açık şubelerden habersiz) — burada gerçek harflere eşlenir:
        # önce kapalı şubeler yeniden kullanılır, sonra sıradaki yeni harf(ler) üretilir.
        plan = plan_sinif_dagilimi(10, 11, eski_yil)
        toplam_sube_ihtiyaci = sum(len(g["subeler"]) for g in plan["alan_gruplari"])
        gercek_harfler = iter(_yeni_subeler_belirle(11, toplam_sube_ihtiyaci, yeni_yil))
        for grup in plan["alan_gruplari"]:
            for sube in grup["subeler"]:
                gercek_harf = next(gercek_harfler)
                for ogr in sube["ogrenciler"]:
                    satirlar.append(SeneSonuOgrenciGecisi(
                        gecis=gecis, ogrenci=ogr,
                        eski_sinif=10, eski_sube=ogr.sube,
                        yeni_sinif=11, yeni_sube=gercek_harf,
                        durum="normal",
                    ))
        for ogr in plan["alan_yok"]:
            satirlar.append(SeneSonuOgrenciGecisi(
                gecis=gecis, ogrenci=ogr,
                eski_sinif=10, eski_sube=ogr.sube,
                yeni_sinif=11, yeni_sube="",
                durum="inceleme_gerekli",
            ))
        for ogr in plan["sinif_tekrari"]:
            satirlar.append(SeneSonuOgrenciGecisi(
                gecis=gecis, ogrenci=ogr,
                eski_sinif=10, eski_sube=ogr.sube,
                yeni_sinif=10, yeni_sube=ogr.sube,
                durum="sinif_tekrari",
            ))

        # 12. sınıf: mezun.
        tekrar_ids_12 = _sinif_tekrari_ids(12)
        for ogr in Ogrenci.objects.filter(aktif=True, sinif=12).order_by("okulno"):
            if ogr.pk in tekrar_ids_12:
                satirlar.append(SeneSonuOgrenciGecisi(
                    gecis=gecis, ogrenci=ogr,
                    eski_sinif=12, eski_sube=ogr.sube,
                    yeni_sinif=12, yeni_sube=ogr.sube,
                    durum="sinif_tekrari",
                ))
            else:
                satirlar.append(SeneSonuOgrenciGecisi(
                    gecis=gecis, ogrenci=ogr,
                    eski_sinif=12, eski_sube=ogr.sube,
                    yeni_sinif=None, yeni_sube="",
                    durum="mezun",
                ))

        SeneSonuOgrenciGecisi.objects.bulk_create(satirlar)

    return gecis


def _arsiv_kalemleri(egitim_yili, arsivlenmis=False):
    """`egitim_yili`ye ait, Sene Sonu Geçişi'nin arşivlediği kayıtları modül bazında
    listeler — hem `gecis_uygula` (arşivlemeyi fiilen uygulamak için) hem de
    `arsiv_ozeti` (önizleme/özet göstermek için — bkz. senesonu/views.py:
    gecis_detay) tarafından kullanılır; tek kaynaktan geldiği için ikisi arasında
    sapma olmaz.

    `arsivlenmis=False` (varsayılan) iken HENÜZ arşivlenmemiş kayıtları (uygulama
    öncesi "arşivlenecek" önizlemesi ve bizzat uygulama için); `arsivlenmis=True`
    iken zaten arşivlenmiş kayıtları (uygulama sonrası özet için) döner.

    Her kalem `{"grup", "etiket", "qs", "update"}` taşır — `update`, kaydı
    arşivlenmiş duruma geçirmek için `qs.update(**update)` ile kullanılır (yalnızca
    `arsivlenmis=False` çağrısında anlamlıdır).
    """
    from dersprogrami.models import DersProgrami
    from devamsizlik.models import OgrenciDevamsizlik
    from faaliyet.models import Faaliyet
    from nobet.models import NobetAtanamayan, NobetGecmisi, NobetGorevi
    from ogrencinobet.models import OgrenciNobetGorevi
    from personeldevamsizlik.models import Devamsizlik
    from sinav.models import SinavBilgisi
    from sorumluluk.models import OncekiDonem, SorumluSinav

    bitis = egitim_yili.egitim_bitis
    bayrak = arsivlenmis  # arsivlendi alanının aranacağı değer

    return [
        {
            "grup": "Öğrenci Nöbeti",
            "etiket": "Öğrenci nöbet görevi",
            "qs": OgrenciNobetGorevi.objects.filter(arsivlendi=bayrak, tarih__lte=bitis),
            "update": {"arsivlendi": True},
        },
        {
            "grup": "Öğretmen Nöbeti",
            "etiket": "Yüklenmiş haftalık nöbet listesi",
            "qs": NobetGorevi.objects.filter(arsivlendi=bayrak).filter(
                Q(egitim_yili=egitim_yili)
                | Q(egitim_yili__isnull=True, uygulama_tarihi__lte=bitis)
            ),
            "update": {"arsivlendi": True},
        },
        {
            "grup": "Öğretmen Nöbeti",
            "etiket": "Ders doldurma kaydı",
            "qs": NobetGecmisi.objects.filter(arsivlendi=bayrak, tarih__date__lte=bitis),
            "update": {"arsivlendi": True},
        },
        {
            "grup": "Öğretmen Nöbeti",
            "etiket": "Atanamayan ders kaydı",
            "qs": NobetAtanamayan.objects.filter(arsivlendi=bayrak, tarih__date__lte=bitis),
            "update": {"arsivlendi": True},
        },
        {
            "grup": "Devamsızlık",
            "etiket": "Öğretmen devamsızlık kaydı",
            "qs": Devamsizlik.objects.filter(arsivlendi=bayrak, baslangic_tarihi__lte=bitis),
            "update": {"arsivlendi": True},
        },
        {
            "grup": "Devamsızlık",
            "etiket": "Öğrenci devamsızlık kaydı",
            "qs": OgrenciDevamsizlik.objects.filter(arsivlendi=bayrak, tarih__lte=bitis),
            "update": {"arsivlendi": True},
        },
        {
            "grup": "Faaliyet",
            "etiket": "Faaliyet kaydı",
            "qs": Faaliyet.objects.filter(arsivlendi=bayrak, tarih__lte=bitis),
            "update": {"arsivlendi": True},
        },
        {
            "grup": "Ders Programı",
            "etiket": "Yüklenmiş haftalık ders programı",
            "qs": DersProgrami.objects.filter(arsivlendi=bayrak).filter(
                Q(egitim_yili=egitim_yili)
                | Q(egitim_yili__isnull=True, uygulama_tarihi__lte=bitis)
            ),
            "update": {"arsivlendi": True},
        },
        {
            "grup": "Ortak Sınav",
            "etiket": "Aktif işaretli ortak sınav",
            "qs": SinavBilgisi.objects.filter(aktif=not bayrak).filter(
                Q(egitim_yili_fk=egitim_yili)
                | Q(egitim_yili_fk__isnull=True, egitim_ogretim_yili=egitim_yili.egitim_yili)
            ),
            "update": {"aktif": False},
        },
        {
            "grup": "Sorumluluk Sınavı",
            "etiket": "Sorumluluk sınavı",
            "qs": SorumluSinav.objects.filter(arsivlendi=bayrak, egitim_yili=egitim_yili),
            "update": {"arsivlendi": True, "arsivlenme_tarihi": timezone.now()},
        },
        {
            "grup": "Sorumluluk Sınavı",
            "etiket": "Geçmiş dönem (adalet puanlaması)",
            "qs": OncekiDonem.objects.filter(arsivlendi=bayrak, egitim_yili=egitim_yili),
            "update": {"arsivlendi": True},
        },
    ]


def arsiv_ozeti(egitim_yili, arsivlenmis=False):
    """`gecis_detay` şablonunda gösterilecek modül bazlı arşiv özeti: her kalem
    için `{"grup", "etiket", "sayi"}`. Bkz. `_arsiv_kalemleri`."""
    return [
        {"grup": k["grup"], "etiket": k["etiket"], "sayi": k["qs"].count()}
        for k in _arsiv_kalemleri(egitim_yili, arsivlenmis=arsivlenmis)
    ]


def gecis_uygula(gecis):
    from ogrenci.models import Ogrenci
    from okul.models import OkulBilgi, SinifSube, SinifSubeYil
    from utility.services.main_services import IstatistikService

    if gecis.uygulandi:
        raise ValueError("Bu geçiş zaten uygulanmış.")

    satirlar = list(gecis.ogrenci_gecisleri.select_related("ogrenci"))
    cozulmemis = [s for s in satirlar if s.durum == "inceleme_gerekli" and not s.yeni_sube]
    if cozulmemis:
        raise ValueError(
            f"{len(cozulmemis)} öğrencinin şubesi henüz belirlenmedi — uygulamadan önce "
            "'İnceleme Gerekli' satırları düzenleyin."
        )

    gerekli_sinif_sube = {
        (s.yeni_sinif, s.yeni_sube) for s in satirlar if s.durum != "mezun" and s.yeni_sube
    }

    with transaction.atomic():
        # Hedef şube yoksa oluşturulur; geçişin ULAŞTIĞI yıl (yeni_egitim_yili) için
        # açık olarak işaretlenir/yeniden açılır — açık/kapalı durumu yıla göre
        # değişebildiğinden (bkz. SinifSube.acik_mi) bu yalnızca o yılı etkiler,
        # şubenin başka yıllardaki durumuna dokunmaz.
        for sinif_no, sube in gerekli_sinif_sube:
            kayit, _ = SinifSube.objects.get_or_create(sinif=sinif_no, sube=sube)
            SinifSubeYil.objects.update_or_create(
                sinif_sube=kayit, egitim_yili=gecis.yeni_egitim_yili, defaults={"acik": True}
            )

        mezun_ids = [s.ogrenci_id for s in satirlar if s.durum == "mezun"]
        if mezun_ids:
            Ogrenci.objects.filter(pk__in=mezun_ids).update(aktif=False)

        guncellenecek = [s for s in satirlar if s.durum != "mezun"]
        ogrenciler = []
        for satir in guncellenecek:
            ogr = satir.ogrenci
            ogr.sinif = satir.yeni_sinif
            ogr.sube = satir.yeni_sube
            ogrenciler.append(ogr)
        if ogrenciler:
            Ogrenci.objects.bulk_update(ogrenciler, ["sinif", "sube"])

        # Eski eğitim-öğretim yılına ait tüm arşivlenebilir modüller tek noktadan
        # (bkz. `_arsiv_kalemleri`) arşivlenir: öğrenci nöbeti, öğretmen nöbeti
        # (yüklenmiş liste + ders doldurma geçmişi + atanamayan kayıtlar), ders
        # programı, öğrenci/öğretmen devamsızlığı, faaliyet, ortak sınav (aktif
        # bayrağı) ve sorumluluk sınavı (+ geçmiş dönem adalet puanlaması). Arşivlenen
        # kayıtların kendisine dokunulmaz, yalnızca ilgili "aktif/güncel" sorgularda
        # artık görünmezler — tam geçmiş, her modülün kendi arşiv/listesi sayfasından
        # erişilebilir olmaya devam eder (bkz. ogrencinobet/views.py,
        # nobet.NobetGoreviQuerySet.aktif, DersProgramiQuerySet.aktif,
        # devamsizlik/faaliyet views.py, sinav/views_ogretmen.py,
        # sorumluluk/services/gorevlendirme_oneri.py, rapor_ozet.py).
        for kalem in _arsiv_kalemleri(gecis.eski_egitim_yili, arsivlenmis=False):
            kalem["qs"].update(**kalem["update"])

        # NobetIstatistik ayrı bir arşiv alanı taşımaz — tamamen arşivlenmemiş
        # NobetGecmisi/NobetAtanamayan üzerinden türetilen bir önbellektir (bkz.
        # IstatistikService.hesapla_ve_kaydet); yukarıdaki arşivlemenin ardından
        # yeniden hesaplandığında yeni eğitim-öğretim yılı için sıfırlanmış (hazır)
        # istatistiklere döner.
        IstatistikService().hesapla_ve_kaydet()

        okul = OkulBilgi.get()
        okul.okul_egtyil = gecis.yeni_egitim_yili
        okul.okul_donem = gecis.yeni_egitim_yili.donemleri.filter(donem=1).first()
        okul.save(update_fields=["okul_egtyil", "okul_donem"])

        gecis.uygulandi = True
        gecis.uygulama_zamani = timezone.now()
        gecis.save(update_fields=["uygulandi", "uygulama_zamani"])

    return gecis
