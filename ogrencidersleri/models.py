from django.db import models


class OgrenciSecmeliDers(models.Model):
    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        on_delete=models.CASCADE,
        related_name="secmeli_dersler",
        verbose_name="Öğrenci",
    )
    ders = models.ForeignKey(
        "secmelidersler.SecmeliDers",
        on_delete=models.CASCADE,
        related_name="secimler",
        verbose_name="Seçmeli Ders",
    )
    secilen_saat = models.PositiveSmallIntegerField(verbose_name="Seçilen Saat")
    olusturma_tarihi = models.DateTimeField(auto_now_add=True)
    guncelleme_tarihi = models.DateTimeField(auto_now=True)

    class Meta:
        # Mevcut tablo yeniden kullanılır — OgrenciSecim'in tablosu
        db_table = "secmelidersler_ogrencisecim"
        unique_together = [("ogrenci", "ders")]
        verbose_name = "Öğrenci Seçmeli Ders Seçimi"
        verbose_name_plural = "Öğrenci Seçmeli Ders Seçimleri"

    def __str__(self):
        return f"{self.ogrenci} — {self.ders.ders_adi} ({self.secilen_saat}s)"


class OgrenciMevcutDers(models.Model):
    """Öğrencinin mevcut eğitim yılında okuduğu dersler (ders programından atanır)."""

    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        on_delete=models.CASCADE,
        related_name="mevcut_dersler",
        verbose_name="Öğrenci",
    )
    ders = models.ForeignKey(
        "okul.DersHavuzu",
        on_delete=models.CASCADE,
        related_name="ogrenci_mevcut",
        verbose_name="Ders",
    )
    haftalik_saat = models.PositiveSmallIntegerField(verbose_name="Haftalık Saat")

    class Meta:
        unique_together = [("ogrenci", "ders")]
        ordering = ["ogrenci", "ders__ders_adi"]
        verbose_name = "Öğrenci Mevcut Ders"
        verbose_name_plural = "Öğrenci Mevcut Dersleri"

    def __str__(self):
        return f"{self.ogrenci} — {self.ders.ders_adi} ({self.haftalik_saat}s)"


class OgrenciZorunluDers(models.Model):
    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        on_delete=models.CASCADE,
        related_name="zorunlu_dersler",
        verbose_name="Öğrenci",
    )
    ortak_ders = models.ForeignKey(
        "secmelidersler.OrtakDers",
        on_delete=models.CASCADE,
        related_name="ogrenci_atamalari",
        verbose_name="Zorunlu Ders",
    )

    class Meta:
        unique_together = [("ogrenci", "ortak_ders")]
        ordering = ["ogrenci", "ortak_ders__sira"]
        verbose_name = "Öğrenci Zorunlu Ders Ataması"
        verbose_name_plural = "Öğrenci Zorunlu Ders Atamaları"

    def __str__(self):
        return f"{self.ogrenci} — {self.ortak_ders.ders_adi}"
