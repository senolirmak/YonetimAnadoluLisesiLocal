from django.db import models
from django.utils import timezone

from ogrenci.models import Ogrenci


class OgrenciDevamsizlik(models.Model):
    ogrenci = models.ForeignKey(
        Ogrenci, on_delete=models.CASCADE, related_name="devamsizliklar", verbose_name="Öğrenci"
    )
    tarih = models.DateField(default=timezone.localdate, verbose_name="Tarih")
    ders_saati = models.IntegerField(verbose_name="Ders Saati")
    ders_adi = models.CharField(max_length=100, verbose_name="Ders Adı")
    ogretmen_adi = models.CharField(max_length=100, verbose_name="Öğretmen")
    aciklama = models.CharField(max_length=200, blank=True, null=True, verbose_name="Açıklama")
    olusturma_zamani = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ogrenci_devamsizlik"
        unique_together = ("ogrenci", "tarih", "ders_saati")
        verbose_name = "Öğrenci Devamsızlık"
        verbose_name_plural = "Öğrenci Devamsızlıkları"
        ordering = ["-tarih", "ders_saati"]

    def __str__(self):
        return f"{self.ogrenci} - {self.tarih} {self.ders_saati}. ders"
