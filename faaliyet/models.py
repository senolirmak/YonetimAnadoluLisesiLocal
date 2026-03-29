from django.db import models

from ogrenci.models import Ogrenci


class Faaliyet(models.Model):
    DURUM_BEKLEMEDE = "beklemede"
    DURUM_ONAYLANDI = "onaylandi"
    DURUM_REDDEDILDI = "reddedildi"
    DURUM_CHOICES = [
        (DURUM_BEKLEMEDE, "Onay Bekliyor"),
        (DURUM_ONAYLANDI, "Onaylandı"),
        (DURUM_REDDEDILDI, "Reddedildi"),
    ]

    konu = models.CharField(max_length=300, verbose_name="Faaliyet Konusu")
    tarih = models.DateField(verbose_name="Tarih")
    yer = models.CharField(max_length=200, verbose_name="Yapıldığı Yer")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    ogretmen = models.ForeignKey(
        "okul.Personel",
        on_delete=models.CASCADE,
        related_name="faaliyetler",
        verbose_name="Öğretmen",
    )
    ogrenciler = models.ManyToManyField(
        Ogrenci,
        blank=True,
        related_name="faaliyetler",
        verbose_name="Katılan Öğrenciler",
    )
    durum = models.CharField(
        max_length=20,
        choices=DURUM_CHOICES,
        default=DURUM_BEKLEMEDE,
        verbose_name="Durum",
    )
    ret_aciklamasi = models.TextField(blank=True, verbose_name="Red Açıklaması")
    devamsizlik_girildi = models.BooleanField(default=False, verbose_name="Devamsızlık Girildi")
    onaylayan_adi = models.CharField(max_length=200, blank=True, verbose_name="Onaylayan")
    onay_zamani = models.DateTimeField(null=True, blank=True, verbose_name="Onay Tarihi")
    olusturma_zamani = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "faaliyet"
        ordering = ["-tarih", "-olusturma_zamani"]
        verbose_name = "Faaliyet"
        verbose_name_plural = "Faaliyetler"

    def __str__(self):
        return f"{self.tarih} — {self.konu}"

    @property
    def ogrenci_sayisi(self):
        return self.ogrenciler.count()


class FaaliyetDersSaati(models.Model):
    faaliyet = models.ForeignKey(
        Faaliyet,
        on_delete=models.CASCADE,
        related_name="ders_saatleri",
    )
    ders_no = models.PositiveSmallIntegerField(verbose_name="Ders No")
    baslangic = models.TimeField(verbose_name="Başlangıç")
    bitis = models.TimeField(verbose_name="Bitiş")

    class Meta:
        db_table = "faaliyet_ders_saati"
        ordering = ["ders_no"]
        unique_together = ("faaliyet", "ders_no")
        verbose_name = "Faaliyet Ders Saati"

    def __str__(self):
        return f"{self.ders_no}. Ders ({self.baslangic:%H:%M}–{self.bitis:%H:%M})"
