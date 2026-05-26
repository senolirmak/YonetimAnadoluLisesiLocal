from django.db import models

SINIF_SEVIYELERI = [(9, "9. Sınıf"), (10, "10. Sınıf"), (11, "11. Sınıf"), (12, "12. Sınıf")]


class OrtakDers(models.Model):
    sinif_seviyesi = models.IntegerField(choices=SINIF_SEVIYELERI, verbose_name="Sınıf Seviyesi")
    ders_adi = models.CharField(max_length=150, verbose_name="Ders Adı")
    haftalik_saat = models.PositiveSmallIntegerField(verbose_name="Haftalık Saat")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        ordering = ["sinif_seviyesi", "sira"]
        verbose_name = "Ortak Ders"
        verbose_name_plural = "Ortak Dersler"

    def __str__(self):
        return f"{self.sinif_seviyesi}. Sınıf — {self.ders_adi}"


class SecmeliDersGrubu(models.Model):
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
        verbose_name = "Seçmeli Ders Grubu"
        verbose_name_plural = "Seçmeli Ders Grupları"

    def __str__(self):
        return f"{self.sinif_seviyesi}. Sınıf — {self.adi}"


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


class Alan(models.Model):
    SINIF_CHOICES = [(11, "11. Sınıf"), (12, "12. Sınıf")]
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
        unique_together = [("sinif_seviyesi", "adi")]
        verbose_name = "Alan"
        verbose_name_plural = "Alanlar"

    def __str__(self):
        return f"{self.sinif_seviyesi}. Sınıf — {self.adi}"


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


class OgrenciSecim(models.Model):
    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        on_delete=models.CASCADE,
        related_name="secmeli_dersler",
        verbose_name="Öğrenci",
    )
    ders = models.ForeignKey(
        SecmeliDers,
        on_delete=models.CASCADE,
        related_name="secimler",
        verbose_name="Seçmeli Ders",
    )
    secilen_saat = models.PositiveSmallIntegerField(verbose_name="Seçilen Saat")
    olusturma_tarihi = models.DateTimeField(auto_now_add=True)
    guncelleme_tarihi = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("ogrenci", "ders")]
        verbose_name = "Öğrenci Seçmeli Ders Seçimi"
        verbose_name_plural = "Öğrenci Seçmeli Ders Seçimleri"

    def __str__(self):
        return f"{self.ogrenci} — {self.ders.ders_adi} ({self.secilen_saat}s)"
