from django.db import models

from ogrenci.models import Ogrenci


class OgrenciNobetGorevi(models.Model):
    ogrenci = models.ForeignKey(
        Ogrenci, on_delete=models.CASCADE, related_name="nobet_gorevleri", verbose_name="Öğrenci"
    )
    tarih = models.DateField(verbose_name="Tarih")
    olusturan = models.CharField(max_length=100, blank=True, verbose_name="Oluşturan")
    olusturma_zamani = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("ogrenci", "tarih")
        ordering = ["-tarih", "ogrenci__sinif", "ogrenci__sube", "ogrenci__soyadi"]
        verbose_name = "Öğrenci Nöbet Görevi"
        verbose_name_plural = "Öğrenci Nöbet Görevleri"

    def __str__(self):
        return f"{self.ogrenci} — {self.tarih}"
