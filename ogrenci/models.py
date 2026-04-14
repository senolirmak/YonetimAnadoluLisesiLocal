from django.db import models
from django.utils import timezone

CINSIYET_CHOICES = (
    ("E", "Erkek"),
    ("K", "Kız"),
)


class Ogrenci(models.Model):
    okulno = models.CharField(max_length=20, unique=True, verbose_name="Okul No")
    sinif = models.IntegerField(verbose_name="Sınıf")
    sube = models.CharField(max_length=2, verbose_name="Şube")
    tckimlikno = models.CharField(max_length=11, unique=True, verbose_name="TC Kimlik No")
    adi = models.CharField(max_length=150, verbose_name="Adı")
    soyadi = models.CharField(max_length=150, verbose_name="Soyadı")
    dogumtarihi = models.DateField(verbose_name="Doğum Tarihi")
    cinsiyet = models.CharField(max_length=1, choices=CINSIYET_CHOICES, verbose_name="Cinsiyet")
    sureksiz_devamsiz = models.BooleanField(
        default=False,
        verbose_name="Sürekli Devamsız",
        help_text="İşaretlenirse mazeret sınavına çağrılmaz.",
    )
    muaf = models.BooleanField(
        default=False,
        verbose_name="Muaf",
        help_text="İşaretlenirse mazeret sınavına alınmaz.",
    )

    class Meta:
        db_table = "ogrenci"
        verbose_name = "Öğrenci"
        verbose_name_plural = "Öğrenciler"
        ordering = ["sinif", "sube", "okulno"]

    @property
    def sinifsube(self):
        return f"{self.sinif}/{self.sube}"

    def __str__(self):
        return f"{self.sinif}/{self.sube} - {self.adi} {self.soyadi}"


class OgrenciDetay(models.Model):
    ogrenci = models.OneToOneField(
        Ogrenci, on_delete=models.CASCADE, related_name="detay", verbose_name="Öğrenci"
    )
    babaadi = models.CharField(max_length=100, blank=True, null=True, verbose_name="Baba Adı")
    anneadi = models.CharField(max_length=100, blank=True, null=True, verbose_name="Anne Adı")
    veli = models.CharField(max_length=100, blank=True, null=True, verbose_name="Veli")
    velitelefon = models.CharField(
        max_length=15, blank=True, null=True, verbose_name="Veli Telefon"
    )
    annetelefon = models.CharField(
        max_length=15, blank=True, null=True, verbose_name="Anne Telefon"
    )
    babatelefon = models.CharField(
        max_length=15, blank=True, null=True, verbose_name="Baba Telefon"
    )

    class Meta:
        db_table = "ogrenci_detay"
        verbose_name = "Öğrenci Detay"
        verbose_name_plural = "Öğrenci Detayları"

    def __str__(self):
        return f"{self.ogrenci} - Detay"


class OgrenciAdres(models.Model):
    ogrenci = models.OneToOneField(
        Ogrenci, on_delete=models.CASCADE, related_name="adres", verbose_name="Öğrenci"
    )
    il = models.CharField(max_length=50, blank=True, null=True, verbose_name="İl")
    ilce = models.CharField(max_length=50, blank=True, null=True, verbose_name="İlçe")
    mahalle = models.CharField(max_length=100, blank=True, null=True, verbose_name="Mahalle")
    postakodu = models.CharField(max_length=10, blank=True, null=True, verbose_name="Posta Kodu")
    adres = models.TextField(blank=True, null=True, verbose_name="Adres")

    class Meta:
        db_table = "ogrenci_adres"
        verbose_name = "Öğrenci Adres"
        verbose_name_plural = "Öğrenci Adresleri"

    def __str__(self):
        return f"{self.ogrenci} - {self.il}/{self.ilce}"


class SinifOturmaDuzeni(models.Model):
    """Sınıfın kalıcı oturma düzeni — rehber öğretmen tarafından düzenlenir."""

    sinif_sube = models.ForeignKey(
        "okul.SinifSube",
        on_delete=models.CASCADE,
        related_name="oturma_duzeni",
        verbose_name="Sınıf/Şube",
    )
    ogrenci = models.ForeignKey(
        Ogrenci,
        on_delete=models.CASCADE,
        related_name="oturma_duzeni",
        verbose_name="Öğrenci",
    )
    # Sıra: 1'den başlar (tahtaya en yakın = 1)
    sira_no = models.PositiveSmallIntegerField(verbose_name="Sıra No")
    # Kolon: 1 = sol, 2 = orta-sol, 3 = orta-sağ, 4 = sağ (max 4 sütun)
    kolon_no = models.PositiveSmallIntegerField(verbose_name="Kolon No")
    guncelleme = models.DateTimeField(auto_now=True, verbose_name="Son Güncelleme")
    guncelleyen = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Güncelleyen",
    )

    class Meta:
        db_table = "sinif_oturma_duzeni"
        unique_together = [("sinif_sube", "sira_no", "kolon_no")]
        verbose_name = "Sınıf Oturma Düzeni"
        verbose_name_plural = "Sınıf Oturma Düzenleri"
        ordering = ["sinif_sube", "sira_no", "kolon_no"]

    def __str__(self):
        return f"{self.sinif_sube} — Sıra {self.sira_no}/{self.kolon_no}: {self.ogrenci.adi} {self.ogrenci.soyadi}"
