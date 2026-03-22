from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class MuduriyetGorusme(models.Model):
    TUR_CHOICES = [
        ("bireysel", "Bireysel Öğrenci"),
        ("veli", "Veli Görüşmesi"),
        ("grup", "Grup Görüşmesi"),
        ("diger", "Diğer"),
    ]

    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="muduriyetcagri_gorusmeleri",
        verbose_name="Öğrenci",
    )
    grup_ogrencileri = models.ManyToManyField(
        "ogrenci.Ogrenci",
        blank=True,
        related_name="muduriyetcagri_grup_gorusmeleri",
        verbose_name="Grup Öğrencileri",
    )
    veli_adi = models.CharField(max_length=200, blank=True, verbose_name="Veli Adı Soyadı")
    veli_telefon = models.CharField(max_length=30, blank=True, verbose_name="Veli Telefonu")
    tarih = models.DateField(verbose_name="Tarih")
    tur = models.CharField(max_length=20, choices=TUR_CHOICES, verbose_name="Görüşme Türü")
    konu = models.CharField(max_length=300, verbose_name="Konu")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    sonuc = models.TextField(blank=True, verbose_name="Alınan Karar / Sonuç")
    takip_tarihi = models.DateField(null=True, blank=True, verbose_name="Takip Tarihi")
    kayit_eden_kullanici = models.ForeignKey(
        User,
        null=True,
        on_delete=models.SET_NULL,
        related_name="muduriyetcagri_gorusmeleri",
        verbose_name="Kaydeden",
    )
    olusturma_zamani = models.DateTimeField(auto_now_add=True)
    guncelleme_zamani = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "muduriyetcagri_gorusme"
        ordering = ["-tarih", "-olusturma_zamani"]
        verbose_name = "Müdüriyet Görüşmesi"
        verbose_name_plural = "Müdüriyet Görüşmeleri"

    def __str__(self):
        ogrenci_adi = str(self.ogrenci) if self.ogrenci else "—"
        return f"{self.tarih} | {self.get_tur_display()} | {ogrenci_adi}"
