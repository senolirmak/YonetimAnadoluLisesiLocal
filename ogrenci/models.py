from django.db import models

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
