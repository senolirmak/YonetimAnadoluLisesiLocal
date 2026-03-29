from django.db import models


class DisiplinGorusme(models.Model):
    TUR_CHOICES = [
        ("bireysel", "Bireysel Öğrenci"),
        ("veli", "Veli Görüşmesi"),
        ("grup", "Grup Görüşmesi"),
    ]

    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="disiplin_gorusmeleri",
        verbose_name="Öğrenci",
    )
    grup_ogrencileri = models.ManyToManyField(
        "ogrenci.Ogrenci",
        blank=True,
        related_name="disiplin_grup_gorusmeleri",
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
    gizli = models.BooleanField(default=False, verbose_name="Gizli Kayıt")
    kayit_eden = models.ForeignKey(
        "okul.Personel",
        null=True,
        on_delete=models.SET_NULL,
        related_name="disiplin_gorusmeleri",
        verbose_name="Kaydeden",
    )
    olusturma_zamani = models.DateTimeField(auto_now_add=True)
    guncelleme_zamani = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "disiplin_gorusme"
        ordering = ["-tarih", "-olusturma_zamani"]
        verbose_name = "Disiplin Görüşmesi"
        verbose_name_plural = "Disiplin Görüşmeleri"

    def __str__(self):
        return f"{self.tarih} | {self.get_tur_display()} | {self.ogrenci or '—'}"
