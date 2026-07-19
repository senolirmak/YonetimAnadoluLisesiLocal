import re

from django.db import models

SINIF_SEVIYELERI = [(9, "9. Sınıf"), (10, "10. Sınıf"), (11, "11. Sınıf"), (12, "12. Sınıf")]

_VARSAYILAN_TOPLAM_SAAT = 40

_SAAT_EKI_RE = re.compile(r"\s*\(\d+\)\s*$")
_YILDIZ_EKI_RE = re.compile(r"\s*\*\s*$")


def normalize_ders_adi(ders_adi):
    """SecmeliDers.ders_adi saat eki taşır ("SEÇMELİ TARİH (1)") ve bazı
    OrtakDers adlarında sondaki '*' işareti bulunur; bu ekler olmadan başka
    sistemlerdeki (TTKB çizelgesi, sorumluluk ders kataloğu vb.) ders
    adlarıyla karşılaştırılabilecek şekilde temizler."""
    metin = _SAAT_EKI_RE.sub("", ders_adi)
    metin = _YILDIZ_EKI_RE.sub("", metin)
    return " ".join(metin.split())


# ---------------------------------------------------------------------------
# Eğitim-Öğretim Yılı yardımcı fonksiyonları
# ---------------------------------------------------------------------------

def get_aktif_egitim_yili():
    """OkulBilgi singleton'dan aktif eğitim-öğretim yılını döndürür."""
    from okul.models import OkulBilgi
    okul = OkulBilgi.objects.select_related("okul_egtyil").first()
    return okul.okul_egtyil if okul else None


# ---------------------------------------------------------------------------
# Sınıf Seviyesi Toplam Saat
# ---------------------------------------------------------------------------

class SinifSeviyeToplamSaat(models.Model):
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sinif_toplam_saatler",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    sinif_seviyesi = models.IntegerField(
        choices=SINIF_SEVIYELERI,
        verbose_name="Sınıf Seviyesi",
    )
    haftalik_toplam_saat = models.PositiveSmallIntegerField(
        default=_VARSAYILAN_TOPLAM_SAAT,
        verbose_name="Haftalık Toplam Saat",
        help_text="Bu sınıf seviyesindeki haftalık toplam ders saati (genellikle 40).",
    )

    class Meta:
        ordering = ["sinif_seviyesi"]
        unique_together = [("egitim_yili", "sinif_seviyesi")]
        verbose_name = "Sınıf Seviyesi Toplam Saat"
        verbose_name_plural = "Sınıf Seviyesi Toplam Saatler"

    def __str__(self):
        yil = f" [{self.egitim_yili}]" if self.egitim_yili else ""
        return f"{self.sinif_seviyesi}. Sınıf — {self.haftalik_toplam_saat} saat{yil}"


def get_toplam_saat(sinif_seviyesi, egitim_yili=None):
    """Sınıf seviyesi için haftalık toplam ders saatini döndürür. Kayıt yoksa 40."""
    if egitim_yili is None:
        egitim_yili = get_aktif_egitim_yili()
    try:
        return SinifSeviyeToplamSaat.objects.get(
            sinif_seviyesi=sinif_seviyesi,
            egitim_yili=egitim_yili,
        ).haftalik_toplam_saat
    except SinifSeviyeToplamSaat.DoesNotExist:
        return _VARSAYILAN_TOPLAM_SAAT


def get_toplam_saat_map(egitim_yili=None):
    """Tüm sınıf seviyeleri için {sinif_seviyesi: toplam_saat} sözlüğü. Eksik kayıtlar 40 varsayılanı alır."""
    if egitim_yili is None:
        egitim_yili = get_aktif_egitim_yili()
    result = {
        obj.sinif_seviyesi: obj.haftalik_toplam_saat
        for obj in SinifSeviyeToplamSaat.objects.filter(egitim_yili=egitim_yili)
    }
    for sv in (9, 10, 11, 12):
        result.setdefault(sv, _VARSAYILAN_TOPLAM_SAAT)
    return result


# ---------------------------------------------------------------------------
# Ortak (Zorunlu) Dersler
# ---------------------------------------------------------------------------

class OrtakDers(models.Model):
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ortak_dersler",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    sinif_seviyesi = models.IntegerField(choices=SINIF_SEVIYELERI, verbose_name="Sınıf Seviyesi")
    ders_adi = models.CharField(max_length=150, verbose_name="Ders Adı")
    haftalik_saat = models.PositiveSmallIntegerField(verbose_name="Haftalık Saat")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    branslar = models.ManyToManyField(
        "okul.Brans",
        blank=True,
        related_name="ortak_dersler",
        verbose_name="Branş(lar)",
        help_text=(
            "Öğretmen ders yükü dağıtımında bu derse aynı branştaki öğretmenler önerilir. "
            "Bazı dersler (örn. GÖRSEL SANATLAR/MÜZİK) birden fazla branştan okutulabilir."
        ),
    )

    class Meta:
        ordering = ["sinif_seviyesi", "sira"]
        unique_together = [("egitim_yili", "sinif_seviyesi", "ders_adi")]
        verbose_name = "Ortak Ders"
        verbose_name_plural = "Ortak Dersler"

    def __str__(self):
        yil = f" [{self.egitim_yili}]" if self.egitim_yili else ""
        return f"{self.sinif_seviyesi}. Sınıf — {self.ders_adi}{yil}"


# ---------------------------------------------------------------------------
# Seçmeli Ders Grupları ve Dersler
# ---------------------------------------------------------------------------

class SecmeliDersGrubu(models.Model):
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="secmeli_ders_gruplari",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    sinif_seviyesi = models.IntegerField(choices=SINIF_SEVIYELERI, verbose_name="Sınıf Seviyesi")
    adi = models.CharField(max_length=100, verbose_name="Grup Adı")
    zorunlu_grup = models.BooleanField(
        default=False,
        verbose_name="Zorunlu Grup",
        help_text=(
            "9-10. sınıf: zorunlu grupların tamamından en az 1 ders seçilmeli. "
            "11-12. sınıf: zorunlu grupların en az ikisinden 1 ders seçilmeli."
        ),
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        ordering = ["sinif_seviyesi", "sira"]
        unique_together = [("egitim_yili", "sinif_seviyesi", "adi")]
        verbose_name = "Seçmeli Ders Grubu"
        verbose_name_plural = "Seçmeli Ders Grupları"

    def __str__(self):
        yil = f" [{self.egitim_yili}]" if self.egitim_yili else ""
        return f"{self.sinif_seviyesi}. Sınıf — {self.adi}{yil}"


class SecmeliDers(models.Model):
    grup = models.ForeignKey(
        SecmeliDersGrubu,
        on_delete=models.CASCADE,
        related_name="dersler",
        verbose_name="Grup",
    )
    ders_adi = models.CharField(max_length=200, verbose_name="Ders Adı")
    saat_secenekleri = models.CharField(
        max_length=50,
        verbose_name="Saat Seçenekleri",
        help_text="Virgülle ayrılmış saat seçenekleri. Tek değer sabit saati gösterir. Örn: '4' veya '2,4' veya '1,2,3'",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    branslar = models.ManyToManyField(
        "okul.Brans",
        blank=True,
        related_name="secmeli_dersler",
        verbose_name="Branş(lar)",
        help_text=(
            "Öğretmen ders yükü dağıtımında bu derse aynı branştaki öğretmenler önerilir. "
            "Bazı dersler (örn. GÖRSEL SANATLAR/MÜZİK) birden fazla branştan okutulabilir."
        ),
    )

    class Meta:
        ordering = ["sira"]
        verbose_name = "Seçmeli Ders"
        verbose_name_plural = "Seçmeli Dersler"

    def __str__(self):
        return f"{self.ders_adi} ({self.saat_secenekleri}s)"

    @property
    def saat_listesi(self):
        return [int(s.strip()) for s in self.saat_secenekleri.split(",") if s.strip().isdigit()]

    @property
    def sabit_saat(self):
        lst = self.saat_listesi
        return lst[0] if len(lst) == 1 else None

    @property
    def secimli_saat(self):
        return len(self.saat_listesi) > 1


# ---------------------------------------------------------------------------
# Alan (11–12. Sınıf)
# ---------------------------------------------------------------------------

class Alan(models.Model):
    SINIF_CHOICES = [(11, "11. Sınıf"), (12, "12. Sınıf")]
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alanlar",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    sinif_seviyesi = models.IntegerField(choices=SINIF_CHOICES, verbose_name="Sınıf Seviyesi")
    adi = models.CharField(max_length=50, verbose_name="Alan Adı")
    dersler = models.ManyToManyField(
        SecmeliDers,
        through="AlanDers",
        blank=True,
        related_name="alanlar",
        verbose_name="Seçmeli Dersler",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        ordering = ["sinif_seviyesi", "sira"]
        unique_together = [("egitim_yili", "sinif_seviyesi", "adi")]
        verbose_name = "Alan"
        verbose_name_plural = "Alanlar"

    def __str__(self):
        yil = f" [{self.egitim_yili}]" if self.egitim_yili else ""
        return f"{self.sinif_seviyesi}. Sınıf — {self.adi}{yil}"


class AlanDers(models.Model):
    alan = models.ForeignKey(Alan, on_delete=models.CASCADE, related_name="alan_dersler")
    ders = models.ForeignKey(SecmeliDers, on_delete=models.CASCADE, related_name="alan_dersler")
    secilen_saat = models.PositiveSmallIntegerField(verbose_name="Seçilen Saat")

    class Meta:
        unique_together = [("alan", "ders")]
        verbose_name = "Alan Dersi"
        verbose_name_plural = "Alan Dersleri"

    def __str__(self):
        return f"{self.alan.adi} — {self.ders.ders_adi} ({self.secilen_saat}s)"


# ---------------------------------------------------------------------------
# Ders — Öğretmen Ataması (gelecek yıl şube/alan ders dağılımı)
# ---------------------------------------------------------------------------

class DersOgretmenAtama(models.Model):
    """
    Gelecek yıl bir şube/alan biriminde okutulacak bir dersi bir öğretmene atar.

    11-12. sınıfta ders paketi ALAN bazında sabittir (OrtakDers + AlanDers);
    birim = (alan, sube_no) — sube_no alan içindeki paralel şube sırasıdır
    (gerçek A/B/C harfi henüz kesinleşmemiştir, bkz. sinif_dagilimi).
    9→10 geçişinde Alan yoktur; birim = mevcut şube harfi (sube), ders listesi
    OrtakDers + o şubedeki öğrencilerin OgrenciSecmeliDers seçimlerinden gelir.
    Bu yüzden alan/sube_no ile sube alanları karşılıklı dışlayıcıdır.
    """

    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ders_ogretmen_atamalari",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    gelecek_sinif = models.IntegerField(choices=SINIF_SEVIYELERI, verbose_name="Gelecek Sınıf Seviyesi")
    alan = models.ForeignKey(
        Alan,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ders_ogretmen_atamalari",
        verbose_name="Alan",
    )
    sube_no = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Şube No",
        help_text="Alan içindeki paralel şube sırası (Şube 1, Şube 2, ...).",
    )
    sube = models.CharField(max_length=2, blank=True, verbose_name="Mevcut Şube Harfi")
    ortak_ders = models.ForeignKey(
        OrtakDers,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ogretmen_atamalari",
        verbose_name="Ortak Ders",
    )
    secmeli_ders = models.ForeignKey(
        SecmeliDers,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ogretmen_atamalari",
        verbose_name="Seçmeli Ders",
    )
    haftalik_saat = models.PositiveSmallIntegerField(verbose_name="Haftalık Saat")
    ogretmen = models.ForeignKey(
        "okul.Personel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ders_atamalari",
        verbose_name="Öğretmen",
    )

    class Meta:
        ordering = ["gelecek_sinif", "alan__sira", "sube", "sube_no"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(ortak_ders__isnull=False, secmeli_ders__isnull=True)
                    | models.Q(ortak_ders__isnull=True, secmeli_ders__isnull=False)
                ),
                name="dersogretmenatama_tek_ders_turu",
            ),
        ]
        # alan/sube_no (11-12) ve sube (9→10) birbirini dışlar; her satır türü
        # kendi kolonunu sabit tutup diğerini ayırt edici olarak kullandığından
        # tek bir kolon seti her iki durumu da doğru ayırt eder.
        unique_together = [
            ("egitim_yili", "gelecek_sinif", "alan", "sube_no", "sube", "ortak_ders"),
            ("egitim_yili", "gelecek_sinif", "alan", "sube_no", "sube", "secmeli_ders"),
        ]
        verbose_name = "Ders Öğretmen Ataması"
        verbose_name_plural = "Ders Öğretmen Atamaları"

    def __str__(self):
        ders = self.ortak_ders.ders_adi if self.ortak_ders_id else self.secmeli_ders.ders_adi
        birim = f"{self.alan.adi} Şube {self.sube_no}" if self.alan_id else f"{self.gelecek_sinif}/{self.sube}"
        ogretmen = self.ogretmen.adi_soyadi if self.ogretmen_id else "— atanmadı —"
        return f"{birim} — {ders} ({self.haftalik_saat}s) — {ogretmen}"

    @property
    def ders(self):
        return self.ortak_ders if self.ortak_ders_id else self.secmeli_ders

    @property
    def birim_etiketi(self):
        return f"{self.alan.adi} — Şube {self.sube_no}" if self.alan_id else f"{self.gelecek_sinif}/{self.sube}"


# ---------------------------------------------------------------------------
# Katalog (global havuz — EÖY bağımsız)
# ---------------------------------------------------------------------------

class OrtakDersHavuzu(models.Model):
    ders_adi = models.CharField(max_length=200, unique=True, verbose_name="Ders Adı")
    derssaati = models.CharField(
        max_length=50,
        default="",
        verbose_name="Ders Saati",
        help_text="Virgülle ayrılmış saat seçenekleri. Örn: '4' veya '2,4' veya '1,2,3'",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    branslar = models.ManyToManyField(
        "okul.Brans",
        blank=True,
        related_name="ortak_ders_havuzu",
        verbose_name="Branş(lar)",
        help_text=(
            "Öğretmen ders yükü dağıtımında bu derse aynı branştaki öğretmenler önerilir. "
            "Bazı dersler birden fazla branştan okutulabilir."
        ),
    )

    class Meta:
        ordering = ["sira", "ders_adi"]
        verbose_name = "Ortak Ders (Havuz)"
        verbose_name_plural = "Ortak Ders Havuzu"

    def __str__(self):
        return self.ders_adi


class SecmeliDersHavuzu(models.Model):
    ders_adi = models.CharField(max_length=200, unique=True, verbose_name="Ders Adı")
    derssaati = models.CharField(
        max_length=50,
        default="",
        verbose_name="Ders Saati",
        help_text="Virgülle ayrılmış saat seçenekleri. Örn: '4' veya '2,4' veya '1,2,3'",
    )
    secimsayisi = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Seçim Sayısı",
        help_text="Öğrencinin bu dersi kaç defa seçebileceği (genellikle 1).",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    branslar = models.ManyToManyField(
        "okul.Brans",
        blank=True,
        related_name="secmeli_ders_havuzu",
        verbose_name="Branş(lar)",
        help_text=(
            "Öğretmen ders yükü dağıtımında bu derse aynı branştaki öğretmenler önerilir. "
            "Bazı dersler birden fazla branştan okutulabilir."
        ),
    )

    class Meta:
        ordering = ["sira", "ders_adi"]
        verbose_name = "Seçmeli Ders (Havuz)"
        verbose_name_plural = "Seçmeli Ders Havuzu"

    def __str__(self):
        return self.ders_adi


# ---------------------------------------------------------------------------
# Sınıf Tekrarı
# ---------------------------------------------------------------------------

class OgrenciSinifTekrari(models.Model):
    ogrenci = models.OneToOneField(
        "ogrenci.Ogrenci",
        on_delete=models.CASCADE,
        related_name="sinif_tekrari",
        verbose_name="Öğrenci",
    )
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sinif_tekrarilar",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sınıf Tekrarı"
        verbose_name_plural = "Sınıf Tekrarları"

    def __str__(self):
        return f"{self.ogrenci} — Sınıf Tekrarı"


# ---------------------------------------------------------------------------
# Tasdikname (Okuma Hakkı Biten Öğrenciler)
# ---------------------------------------------------------------------------

class OgrenciTasdikname(models.Model):
    ogrenci = models.OneToOneField(
        "ogrenci.Ogrenci",
        on_delete=models.CASCADE,
        related_name="tasdikname",
        verbose_name="Öğrenci",
    )
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tasdiknameler",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    tarih = models.DateField(null=True, blank=True, verbose_name="Tasdikname Tarihi")
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tasdikname"
        verbose_name_plural = "Tasdiknameler"

    def __str__(self):
        return f"{self.ogrenci} — Tasdikname"


# ---------------------------------------------------------------------------
# Öğrenci Dönem Ağırlıklı Ortalaması
# ---------------------------------------------------------------------------

class OgrenciOrtalama(models.Model):
    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        on_delete=models.CASCADE,
        related_name="ortalamalar",
        verbose_name="Öğrenci",
    )
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ogrenci_ortalamalar",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    a_ortalama = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Ağırlıklı Ortalama",
    )
    guncelleme = models.DateTimeField(auto_now=True, verbose_name="Güncellenme")

    class Meta:
        unique_together = [("ogrenci", "egitim_yili")]
        ordering = ["ogrenci__okulno"]
        verbose_name = "Öğrenci Ortalaması"
        verbose_name_plural = "Öğrenci Ortalamaları"

    def __str__(self):
        return f"{self.ogrenci} — {self.a_ortalama}"
