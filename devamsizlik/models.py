from django.db import models
from django.utils import timezone

from ogrenci.models import Ogrenci


class OgrenciDevamsizlik(models.Model):
    ogrenci = models.ForeignKey(
        Ogrenci, on_delete=models.CASCADE, related_name="devamsizliklar", verbose_name="Öğrenci"
    )
    tarih = models.DateField(default=timezone.localdate, verbose_name="Tarih")
    ders_saati = models.ForeignKey(
        "okul.DersSaatleri",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="devamsizlik",
        verbose_name="Ders Saati",
    )
    ders_adi = models.CharField(max_length=100, verbose_name="Ders Adı")
    ogretmen_adi = models.CharField(max_length=100, verbose_name="Öğretmen")
    aciklama = models.CharField(max_length=200, blank=True, null=True, verbose_name="Açıklama")
    olusturma_zamani = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ogrenci_devamsizlik"
        unique_together = ("ogrenci", "tarih", "ders_saati")
        verbose_name = "Öğrenci Devamsızlık"
        verbose_name_plural = "Öğrenci Devamsızlıkları"
        ordering = ["-tarih", "ders_saati__derssaati_no"]

    def __str__(self):
        ds_no = self.ders_saati.derssaati_no if self.ders_saati else "—"
        return f"{self.ogrenci} - {self.tarih} {ds_no}. ders"
