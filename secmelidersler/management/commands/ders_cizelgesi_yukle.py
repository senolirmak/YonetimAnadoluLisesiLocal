"""
Haftalık Ders Çizelgesi PDF'inden Ortak Dersler ve Seçmeli Dersler verilerini yükler.

Kullanım:
    python manage.py ders_cizelgesi_yukle /yol/dosya.pdf
    python manage.py ders_cizelgesi_yukle /yol/dosya.pdf --temizle
    python manage.py ders_cizelgesi_yukle /yol/dosya.pdf --siniflar 11 12
    python manage.py ders_cizelgesi_yukle /yol/dosya.pdf --kuru-calistir
"""

import re

from django.core.management.base import BaseCommand, CommandError

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore

from secmelidersler.models import OrtakDers, SecmeliDers, SecmeliDersGrubu

# Sınıf → tablo sütun indeksi
_SINIF_KOLON = {9: 3, 10: 4, 11: 5, 12: 6}

# Grup sırası ve zorunluluk bilgisi
_GRUP_META = {
    "AKADEMİK ÇALIŞMALAR":   {"sira": 1, "zorunlu": False},
    "İNSAN, TOPLUM VE BİLİM": {"sira": 2, "zorunlu": True},
    "DİN, AHLAK VE DEĞER":    {"sira": 3, "zorunlu": True},
    "KÜLTÜR, SANAT VE SPOR":  {"sira": 4, "zorunlu": True},
}

_GRUP_SIRALI = list(_GRUP_META.keys())

# Atlanan satırlar
_ATLA = {
    "ORTAK DERS SAATİ TOPLAMI",
    "SEÇİLEBİLECEK DERS SAATİ SAYISI",
    "TOPLAM DERS SAATİ",
    "REHBERLİK VE YÖNLENDİRME",
    "SOSYAL SORUMLULUK PROGRAMI",
    "HAYAT BOYU ÖĞRENME/SERTİFİKASYON",
}


# ──────────────────────────────────────────────────────────
# Yardımcı fonksiyonlar
# ──────────────────────────────────────────────────────────

def _normalize_metin(s):
    if not s:
        return ""
    return " ".join(s.replace("\n", " ").split()).strip()


def _grup_tespit(metin):
    """
    Hücre metninden grup adını tespit eder.
    Kısmi eşleşmelere de (örn. 'VE BİLİM', 'İNSAN, TOPLUM') yanıt verir.
    """
    t = metin.upper()
    if "AKADEMİK" in t or "ÇALIŞMALAR" in t:
        return "AKADEMİK ÇALIŞMALAR"
    if "İNSAN" in t or "BİLİM" in t:
        return "İNSAN, TOPLUM VE BİLİM"
    if "DİN" in t or "AHLAK" in t or "DEĞER" in t:
        return "DİN, AHLAK VE DEĞER"
    if "KÜLTÜR" in t or "SANAT" in t or ("SPOR" in t and "EĞİTİMİ" not in t):
        return "KÜLTÜR, SANAT VE SPOR"
    return None


def _saat_coz(deger):
    """
    '-' veya None  → None (bu sınıfta yok)
    '2'            → '2'  (sabit saat)
    '(1)(2)'       → '1,2'
    '(2)(10)(12)'  → '2,10,12'
    """
    if not deger or deger.strip() in ("-", ""):
        return None
    d = deger.strip()
    if "(" in d:
        sayilar = re.findall(r"\((\d+)\)", d)
        return ",".join(sayilar) if sayilar else None
    try:
        int(d)
        return d
    except ValueError:
        return None


# ──────────────────────────────────────────────────────────
# PDF ayrıştırma
# ──────────────────────────────────────────────────────────

def _pdf_tablo_oku(pdf_yolu):
    if pdfplumber is None:
        raise CommandError(
            "pdfplumber kütüphanesi kurulu değil.\n"
            "Kurulum: pip install pdfplumber"
        )
    try:
        with pdfplumber.open(pdf_yolu) as pdf:
            tablolar = pdf.pages[0].extract_tables()
    except FileNotFoundError:
        raise CommandError(f"Dosya bulunamadı: {pdf_yolu}")
    if not tablolar:
        raise CommandError("PDF'de tablo bulunamadı.")
    return tablolar[0]


def _ortak_dersleri_coz(tablo, siniflar):
    """
    Tablo satırları 4-18 arası Ortak Dersleri içerir.
    Dönüş: {sinif: [(ders_adi, haftalik_saat, sira), ...]}
    """
    sonuc = {s: [] for s in siniflar}
    sira = 1
    for satir in tablo[4:20]:
        ders_adi = _normalize_metin(satir[1])
        if not ders_adi or any(a in ders_adi.upper() for a in _ATLA):
            continue
        for sinif in siniflar:
            kolon = _SINIF_KOLON[sinif]
            deger = satir[kolon] if kolon < len(satir) else None
            saat_str = _saat_coz(deger)
            if saat_str is None:
                continue
            try:
                saat = int(saat_str)
            except ValueError:
                continue
            sonuc[sinif].append((ders_adi, saat, sira))
        sira += 1
    return sonuc


def _secmeli_dersleri_coz(tablo, siniflar):
    """
    Tablo satırları 20-64 arası Seçmeli Dersleri içerir.

    Tablo yapısındaki özellik: 'İNSAN, TOPLUM VE BİLİM' grup adı, bloğun
    ORTASINDA (satır 42-43) görünür; blok satır 34'ten başlar. Algoritma,
    gruba atanamayan dersleri biriktirir ve grup adı görünür görünmez geriye
    dönük olarak atar.

    Dönüş: {grup_adi: [(ders_adi, {sinif: saat_str}), ...]}
    """
    secmeli_satirlar = tablo[20:65]

    mevcut_grup = None
    bekleyen = []           # henüz gruba atanamamış (ders_adi, saatler_dict) listesi
    grup_dersleri = {}      # {grup_adi: [(ders_adi, saatler_dict), ...]}

    for satir in secmeli_satirlar:
        col1 = _normalize_metin(satir[1])
        col2 = _normalize_metin(satir[2])

        # ── Grup adı tespiti ──
        if col1:
            yeni_grup = _grup_tespit(col1)
            if yeni_grup and yeni_grup != mevcut_grup:
                # Bekleyen dersleri geriye dönük olarak bu gruba ata
                if bekleyen:
                    grup_dersleri.setdefault(yeni_grup, []).extend(bekleyen)
                    bekleyen = []
                mevcut_grup = yeni_grup

        # ── Ders satırı mı? ──
        if not col2 or col2 in _ATLA:
            continue

        saatler = {}
        for sinif in siniflar:
            kolon = _SINIF_KOLON[sinif]
            deger = satir[kolon] if kolon < len(satir) else None
            saat_str = _saat_coz(deger)
            if saat_str:
                saatler[sinif] = saat_str

        if not saatler:
            continue  # Hiçbir sınıf için geçerli saat yok

        girdi = (col2, saatler)
        if mevcut_grup:
            grup_dersleri.setdefault(mevcut_grup, []).append(girdi)
        else:
            bekleyen.append(girdi)

    if bekleyen:
        return grup_dersleri, bekleyen
    return grup_dersleri, []


# ──────────────────────────────────────────────────────────
# Management command
# ──────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Haftalık ders çizelgesi PDF'inden Ortak Dersler ve Seçmeli Dersler verilerini yükler."

    def add_arguments(self, parser):
        parser.add_argument("pdf", type=str, help="PDF dosya yolu")
        parser.add_argument(
            "--temizle",
            action="store_true",
            help="Yükleme öncesi seçilen sınıf verilerini siler.",
        )
        parser.add_argument(
            "--siniflar",
            nargs="+",
            type=int,
            default=[9, 10, 11, 12],
            metavar="SINIF",
            help="Yüklenecek sınıf seviyeleri (varsayılan: 9 10 11 12)",
        )
        parser.add_argument(
            "--kuru-calistir",
            action="store_true",
            help="Veritabanına yazmadan sadece ayrıştırma sonuçlarını gösterir.",
        )

    def handle(self, *args, **options):
        pdf_yolu = options["pdf"]
        siniflar = sorted(set(options["siniflar"]))
        temizle = options["temizle"]
        kuru = options["kuru_calistir"]

        self.stdout.write(f"PDF okunuyor: {pdf_yolu}")
        tablo = _pdf_tablo_oku(pdf_yolu)
        self.stdout.write(f"  {len(tablo)} satır bulundu.")

        # ── Ortak dersler ──
        ortak = _ortak_dersleri_coz(tablo, siniflar)

        # ── Seçmeli dersler ──
        secmeli, bekleyen = _secmeli_dersleri_coz(tablo, siniflar)

        if bekleyen:
            self.stdout.write(
                self.style.WARNING(
                    f"  UYARI: {len(bekleyen)} ders herhangi bir gruba atanamadı: "
                    + ", ".join(d for d, _ in bekleyen)
                )
            )

        # ── Kuru çalıştırma raporu ──
        if kuru:
            self._rapor_yazdir(ortak, secmeli, siniflar)
            return

        # ── Temizle ──
        if temizle:
            for sinif in siniflar:
                silinecek_od = OrtakDers.objects.filter(sinif_seviyesi=sinif).count()
                silinecek_sg = SecmeliDersGrubu.objects.filter(sinif_seviyesi=sinif).count()
                OrtakDers.objects.filter(sinif_seviyesi=sinif).delete()
                SecmeliDersGrubu.objects.filter(sinif_seviyesi=sinif).delete()
                self.stdout.write(
                    f"  {sinif}. sınıf: {silinecek_od} ortak ders, "
                    f"{silinecek_sg} grup silindi."
                )

        # ── Ortak dersler kaydet ──
        self._ortak_kaydet(ortak, siniflar, temizle)

        # ── Seçmeli dersler kaydet ──
        self._secmeli_kaydet(secmeli, siniflar, temizle)

        self.stdout.write(self.style.SUCCESS("\nYükleme başarıyla tamamlandı."))

    # ── Yardımcı: kaydetme ──────────────────────────────

    def _ortak_kaydet(self, ortak, siniflar, temizle):
        for sinif in siniflar:
            dersler = ortak.get(sinif, [])
            sayac = 0
            for ders_adi, saat, sira in dersler:
                if temizle:
                    OrtakDers.objects.create(
                        sinif_seviyesi=sinif, ders_adi=ders_adi,
                        haftalik_saat=saat, sira=sira,
                    )
                else:
                    OrtakDers.objects.update_or_create(
                        sinif_seviyesi=sinif, ders_adi=ders_adi,
                        defaults={"haftalik_saat": saat, "sira": sira},
                    )
                sayac += 1
            if sayac:
                self.stdout.write(f"  Ortak — {sinif}. sınıf: {sayac} ders kaydedildi.")

    def _secmeli_kaydet(self, secmeli, siniflar, temizle):
        for sinif in siniflar:
            grup_sira = 1
            for grup_adi in _GRUP_SIRALI:
                ders_listesi = secmeli.get(grup_adi, [])
                # Bu sınıf için dersler
                sinif_dersleri = [
                    (dn, saatler[sinif])
                    for dn, saatler in ders_listesi
                    if sinif in saatler
                ]
                if not sinif_dersleri:
                    continue

                meta = _GRUP_META[grup_adi]
                if temizle:
                    grup_obj = SecmeliDersGrubu.objects.create(
                        sinif_seviyesi=sinif, adi=grup_adi,
                        zorunlu_grup=meta["zorunlu"], sira=grup_sira,
                    )
                else:
                    grup_obj, _ = SecmeliDersGrubu.objects.get_or_create(
                        sinif_seviyesi=sinif, adi=grup_adi,
                        defaults={"zorunlu_grup": meta["zorunlu"], "sira": grup_sira},
                    )

                ders_sira = 1
                for ders_adi, saat_str in sinif_dersleri:
                    if temizle:
                        SecmeliDers.objects.create(
                            grup=grup_obj, ders_adi=ders_adi,
                            saat_secenekleri=saat_str, sira=ders_sira,
                        )
                    else:
                        SecmeliDers.objects.update_or_create(
                            grup=grup_obj, ders_adi=ders_adi,
                            defaults={"saat_secenekleri": saat_str, "sira": ders_sira},
                        )
                    ders_sira += 1

                self.stdout.write(
                    f"  Seçmeli — {sinif}. sınıf / {grup_adi}: {len(sinif_dersleri)} ders."
                )
                grup_sira += 1

    def _rapor_yazdir(self, ortak, secmeli, siniflar):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("KURU ÇALIŞTIRMA RAPORU (veritabanına yazılmadı)")
        self.stdout.write("=" * 60)

        for sinif in siniflar:
            self.stdout.write(f"\n── {sinif}. SINIF ──")

            od = ortak.get(sinif, [])
            self.stdout.write(f"  Ortak dersler ({len(od)} ders):")
            for ders_adi, saat, _ in od:
                self.stdout.write(f"    {ders_adi}: {saat} saat")

            self.stdout.write(f"  Seçmeli dersler:")
            for grup_adi in _GRUP_SIRALI:
                ders_listesi = secmeli.get(grup_adi, [])
                sinif_dersleri = [(dn, s[sinif]) for dn, s in ders_listesi if sinif in s]
                if not sinif_dersleri:
                    continue
                self.stdout.write(f"    [{grup_adi}]")
                for ders_adi, saat_str in sinif_dersleri:
                    self.stdout.write(f"      {ders_adi}: {saat_str}")
