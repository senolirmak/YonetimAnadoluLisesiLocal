from django.db import models

SINIF_SEVIYELERI = [(9, "9. Sınıf"), (10, "10. Sınıf"), (11, "11. Sınıf"), (12, "12. Sınıf")]

_VARSAYILAN_TOPLAM_SAAT = 40


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

    class Meta:
        ordering = ["sira", "ders_adi"]
        verbose_name = "Seçmeli Ders (Havuz)"
        verbose_name_plural = "Seçmeli Ders Havuzu"

    def __str__(self):
        return self.ders_adi
