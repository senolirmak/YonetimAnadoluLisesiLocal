from django.db import models


def sinav_media_upload_path(instance, filename):
    return f"sinavmedia/{instance.takvim.tarih}/{instance.takvim.pk}_{instance.seviye}/{filename}"


class SinavMedia(models.Model):
    SEVIYE_CHOICES = [(9, "9. Sınıf"), (10, "10. Sınıf"), (11, "11. Sınıf"), (12, "12. Sınıf")]

    takvim = models.ForeignKey(
        "sinav.Takvim",
        on_delete=models.CASCADE,
        related_name="medyalar",
        limit_choices_to={"sinav_turu": "Uygulama"},
    )
    seviye = models.IntegerField(choices=SEVIYE_CHOICES)
    dosya = models.FileField(upload_to=sinav_media_upload_path)
    aciklama = models.CharField(max_length=300, blank=True, default="")
    serbest = models.BooleanField(
        default=False,
        help_text="İşaretlenirse sınav saati kısıtı kaldırılır, her zaman oynatılabilir.",
    )

    class Meta:
        ordering = ["takvim__tarih", "takvim__saat", "seviye"]
        unique_together = [("takvim", "seviye")]
        verbose_name = "Sınav Medyası"
        verbose_name_plural = "Sınav Medyaları"

    def __str__(self):
        return f"{self.takvim} – {self.get_seviye_display()}"
