from django.conf import settings
from django.db import models
from django.utils import timezone


class SeneSonuGecisi(models.Model):
    """Bir eğitim-öğretim yılından bir sonrakine öğrenci sınıf/şube atlatma işlemi."""

    eski_egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        related_name="sene_sonu_gecisleri_eski",
        verbose_name="Eski Eğitim-Öğretim Yılı",
    )
    yeni_egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        related_name="sene_sonu_gecisleri_yeni",
        verbose_name="Yeni Eğitim-Öğretim Yılı",
    )
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sene_sonu_gecisleri",
        verbose_name="Oluşturan",
    )
    olusturulma_zamani = models.DateTimeField(default=timezone.now)
    uygulandi = models.BooleanField(default=False, verbose_name="Uygulandı")
    uygulama_zamani = models.DateTimeField(null=True, blank=True, verbose_name="Uygulama Zamanı")

    class Meta:
        db_table = "senesonu_gecisi"
        verbose_name = "Sene Sonu Geçişi"
        verbose_name_plural = "Sene Sonu Geçişleri"
        ordering = ["-olusturulma_zamani"]

    def __str__(self):
        return f"{self.eski_egitim_yili} → {self.yeni_egitim_yili}"


class SeneSonuOgrenciGecisi(models.Model):
    DURUM_CHOICES = [
        ("normal", "Normal Geçiş"),
        ("sinif_tekrari", "Sınıf Tekrarı"),
        ("mezun", "Mezun"),
        ("inceleme_gerekli", "İnceleme Gerekli"),
    ]

    gecis = models.ForeignKey(
        SeneSonuGecisi,
        on_delete=models.CASCADE,
        related_name="ogrenci_gecisleri",
        verbose_name="Sene Sonu Geçişi",
    )
    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        on_delete=models.PROTECT,
        related_name="sene_sonu_gecisleri",
        verbose_name="Öğrenci",
    )
    eski_sinif = models.IntegerField(verbose_name="Eski Sınıf")
    eski_sube = models.CharField(max_length=2, verbose_name="Eski Şube")
    yeni_sinif = models.IntegerField(null=True, blank=True, verbose_name="Yeni Sınıf")
    yeni_sube = models.CharField(max_length=2, blank=True, verbose_name="Yeni Şube")
    durum = models.CharField(max_length=20, choices=DURUM_CHOICES, verbose_name="Durum")

    class Meta:
        db_table = "senesonu_ogrenci_gecisi"
        verbose_name = "Sene Sonu Öğrenci Geçişi"
        verbose_name_plural = "Sene Sonu Öğrenci Geçişleri"
        unique_together = [("gecis", "ogrenci")]
        ordering = ["eski_sinif", "eski_sube", "ogrenci__okulno"]

    def __str__(self):
        return f"{self.ogrenci} — {self.get_durum_display()}"
