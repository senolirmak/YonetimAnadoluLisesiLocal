from django.db import models
from django.utils import timezone

GUNLER = (
    ("Monday", "Pazartesi"),
    ("Tuesday", "Salı"),
    ("Wednesday", "Çarşamba"),
    ("Thursday", "Perşembe"),
    ("Friday", "Cuma"),
    ("Saturday", "Cumartesi"),
    ("Sunday", "Pazar"),
)


class NobetDersProgrami(models.Model):
    gun = models.CharField(max_length=10, choices=GUNLER)
    giris_saat = models.TimeField()
    cikis_saat = models.TimeField()
    ders_adi = models.CharField(max_length=100)
    sinif_sube = models.ForeignKey(
        "nobet.SinifSube",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dersprogrami",
        verbose_name="Sınıf/Şube",
    )
    ders_saati = models.IntegerField()
    ders_saati_adi = models.CharField(max_length=10)
    uygulama_tarihi = models.DateField(default=timezone.now)
    ogretmen = models.ForeignKey(
        "nobet.NobetPersonel", on_delete=models.CASCADE, related_name="dersprogrami"
    )

    class Meta:
        db_table = "nobet_dersprogrami"
        verbose_name = "Ders Programı"
        verbose_name_plural = "Haftalık Ders Programı"
