from django.db import models

from ogrenci.models import Ogrenci


class OgrenciNobetGorevi(models.Model):
    ogrenci = models.ForeignKey(
        Ogrenci, on_delete=models.CASCADE, related_name="nobet_gorevleri", verbose_name="Öğrenci"
    )
    tarih = models.DateField(verbose_name="Tarih")
    olusturan = models.CharField(max_length=100, blank=True, verbose_name="Oluşturan")
    olusturma_zamani = models.DateTimeField(auto_now_add=True)
    arsivlendi = models.BooleanField(
        default=False,
        verbose_name="Arşivlendi",
        help_text=(
            "Sene Sonu Geçişi uygulandığında geçmiş eğitim-öğretim yılına ait görevler "
            "otomatik olarak arşivlenir; arşivlenen görevler öğrenciyi yeni yılda nöbetçi "
            "seçiminde engellemez, yalnızca bilgi amaçlı gösterilir."
        ),
    )

    class Meta:
        unique_together = ("ogrenci", "tarih")
        ordering = ["-tarih", "ogrenci__sinif", "ogrenci__sube", "ogrenci__soyadi"]
        verbose_name = "Öğrenci Nöbet Görevi"
        verbose_name_plural = "Öğrenci Nöbet Görevleri"

    def __str__(self):
        return f"{self.ogrenci} — {self.tarih}"
