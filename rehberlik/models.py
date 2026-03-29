from django.db import models


class Gorusme(models.Model):
    TUR_CHOICES = [
        ("bireysel", "Bireysel Öğrenci"),
        ("veli", "Veli Görüşmesi"),
        ("grup", "Grup Görüşmesi"),
        ("ogretmen", "Öğretmen Görüşmesi"),
        ("diger", "Diğer"),
    ]

    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gorusmeler",
        verbose_name="Öğrenci",
    )
    grup_ogrencileri = models.ManyToManyField(
        "ogrenci.Ogrenci",
        blank=True,
        related_name="grup_gorusmeleri",
        verbose_name="Grup Öğrencileri",
    )
    gorusulen_ogretmen = models.ForeignKey(
        "okul.Personel",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gorusulen_gorusmeler",
        verbose_name="Görüşülen Öğretmen",
    )
    veli_adi = models.CharField(max_length=200, blank=True, verbose_name="Veli Adı Soyadı")
    veli_telefon = models.CharField(max_length=30, blank=True, verbose_name="Veli Telefonu")
    tarih = models.DateField(verbose_name="Tarih")
    tur = models.CharField(
        max_length=20,
        choices=TUR_CHOICES,
        verbose_name="Görüşme Türü",
    )
    konu = models.CharField(max_length=300, verbose_name="Konu")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    sonuc = models.TextField(blank=True, verbose_name="Alınan Önlem / Sonuç")
    takip_tarihi = models.DateField(
        null=True,
        blank=True,
        verbose_name="Takip Tarihi",
    )
    gizli = models.BooleanField(
        default=False,
        verbose_name="Gizli Kayıt",
    )
    rehber = models.ForeignKey(
        "okul.Personel",
        null=True,
        on_delete=models.SET_NULL,
        related_name="gorusmeler",
        verbose_name="Rehber Öğretmen",
    )
    olusturma_zamani = models.DateTimeField(auto_now_add=True)
    guncelleme_zamani = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rehberlik_gorusme"
        ordering = ["-tarih", "-olusturma_zamani"]
        verbose_name = "Görüşme"
        verbose_name_plural = "Görüşmeler"

    def __str__(self):
        ogrenci_adi = str(self.ogrenci) if self.ogrenci else "—"
        return f"{self.tarih} | {self.get_tur_display()} | {ogrenci_adi}"

    def get_tur_label(self):
        return dict(self.TUR_CHOICES).get(self.tur, self.tur)
