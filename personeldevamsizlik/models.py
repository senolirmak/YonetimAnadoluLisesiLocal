from datetime import datetime, timedelta

from django.db import models
from django.utils import timezone


class Devamsizlik(models.Model):
    baslangic_tarihi = models.DateField()
    bitis_tarihi = models.DateField(null=True, blank=True)
    DEVAMSIZLIK_TURU_CHOICES = (
        (0, "Kısmı Devamsız"),
        (1, "Raporlu"),
        (2, "Mazeret İzinli/İzinli"),
        (3, "Görevli İzinli"),
    )
    devamsiz_tur = models.IntegerField(choices=DEVAMSIZLIK_TURU_CHOICES, default=0)
    sure = models.IntegerField(default=1)
    aciklama = models.CharField(max_length=200, null=True, blank=True)
    ders_saatleri = models.CharField(
        max_length=50,
        default="1,2,3,4,5,6,7,8",
        help_text="Virgülle ayrılmış ders saatleri (Örn: 1,2,3)",
    )
    gorevlendirme_yapilsin = models.BooleanField(
        default=True,
        help_text="Bu devamsızlık için boş derslere nöbetçi öğretmen ataması yapılsın mı?",
    )
    ogretmen = models.ForeignKey(
        "nobet.NobetOgretmen", on_delete=models.CASCADE, related_name="devamsizlik"
    )

    class Meta:
        db_table = "nobet_devamsizlik"
        verbose_name = "Devamsızlık Kaydı"
        verbose_name_plural = "Devamsızlık Kayıtları"

    def save(self, *args, **kwargs):
        if self.baslangic_tarihi and self.sure:
            self.bitis_tarihi = self.baslangic_tarihi + timedelta(days=self.sure - 1)
        super().save(*args, **kwargs)

    @property
    def goreve_baslama_tarihi(self):
        if self.baslangic_tarihi and self.sure:
            return self.baslangic_tarihi + timedelta(days=self.sure)
        return None

    @property
    def durum(self):
        if self.goreve_baslama_tarihi:
            karsilastirma_tarihi = self.goreve_baslama_tarihi
            if isinstance(karsilastirma_tarihi, datetime):
                karsilastirma_tarihi = karsilastirma_tarihi.date()
            if karsilastirma_tarihi > timezone.now().date():
                return "İzinli"
            return "Göreve Başladı"
        return ""
