from django.contrib.auth.models import User
from django.db import models

from nobet.models import SinifSube


class Duyuru(models.Model):
    sinif = models.ForeignKey(
        SinifSube, on_delete=models.CASCADE, verbose_name="Sınıf/Şube", related_name="duyurular"
    )
    tarih = models.DateField(verbose_name="Duyuru Tarihi")
    ders_saati = models.PositiveSmallIntegerField(verbose_name="Ders Saati")
    mesaj = models.TextField(verbose_name="Duyuru Mesajı")

    olusturan = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Oluşturan"
    )
    olusturulma_zaman = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Duyuru"
        verbose_name_plural = "Duyurular"
        ordering = ["-tarih", "ders_saati"]
        # Eğer bir sınıfa aynı tarihte aynı saate sadece 1 duyuru girilmesini isterseniz alttaki yorumu kaldırın:
        # unique_together = ('sinif', 'tarih', 'ders_saati')

    def __str__(self):
        return f"{self.sinif} - {self.tarih.strftime('%d.%m.%Y')} - {self.ders_saati}. Ders"
