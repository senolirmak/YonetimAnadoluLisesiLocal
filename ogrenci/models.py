from django.db import models
from django.utils import timezone

CINSIYET_CHOICES = (
    ("E", "Erkek"),
    ("K", "Kız"),
)

AYRILMA_SEBEBI_CHOICES = (
    ("nakil", "Nakil"),
    ("ogrenim_hakki", "Öğrenim Hakkını Tamamladı"),
    ("mesem", "Mesem Sistemine Kayıt"),
    ("yurtdisi", "Yurt Dışına Çıktı"),
    ("vefat", "Vefat"),
    ("diger", "Diğer"),
)


class Ogrenci(models.Model):
    okulno = models.PositiveIntegerField(unique=True, verbose_name="Okul No")
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
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
        help_text="Tasdikname alan (öğrenim hakkını kullanmış) öğrenciler için otomatik olarak "
        "pasife alınır ve aktif öğrenci listelerinden çıkarılır.",
    )
    sectigi_alan = models.CharField(
        max_length=20,
        default="YOK",
        blank=True,
        verbose_name="Seçtiği Alan",
        help_text="11-12. sınıfta MF/TM/DİL gibi seçilen alan adı; 9-10. sınıf ve alan "
        "seçimi yapılmamış öğrenciler için 'YOK'.",
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


class OgrenciMuaf(models.Model):
    """Öğrencinin belirli bir dersten muaf olduğunu kaydeder."""
    ogrenci = models.ForeignKey(
        Ogrenci, on_delete=models.CASCADE,
        related_name="muaf_dersler", verbose_name="Öğrenci",
    )
    ders = models.ForeignKey(
        "okul.DersHavuzu", on_delete=models.CASCADE,
        related_name="+", verbose_name="Ders",
    )
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Eğitim-Öğretim Yılı",
    )

    class Meta:
        unique_together = [("egitim_yili", "ogrenci", "ders")]
        ordering = ["ogrenci", "ders__ders_adi"]
        verbose_name = "Öğrenci Muaf Ders"
        verbose_name_plural = "Öğrenci Muaf Dersleri"

    def __str__(self):
        return f"{self.ogrenci} — {self.ders.ders_adi} (Muaf)"


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
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Eğitim-Öğretim Yılı",
    )

    class Meta:
        db_table = "sinif_oturma_duzeni"
        unique_together = [("egitim_yili", "sinif_sube", "sira_no", "kolon_no")]
        verbose_name = "Sınıf Oturma Düzeni"
        verbose_name_plural = "Sınıf Oturma Düzenleri"
        ordering = ["sinif_sube", "sira_no", "kolon_no"]

    def __str__(self):
        return f"{self.sinif_sube} — Sıra {self.sira_no}/{self.kolon_no}: {self.ogrenci.adi} {self.ogrenci.soyadi}"


class OgrenciAyrilma(models.Model):
    """Öğrencinin okuldan ayrılma bilgisi. Kaydedilince ilgili öğrenci otomatik
    olarak pasife alınır (aktif=False); kayıt silinince tekrar aktif hale gelir."""

    ogrenci = models.OneToOneField(
        Ogrenci,
        on_delete=models.CASCADE,
        related_name="ayrilma",
        verbose_name="Öğrenci",
    )
    sebep = models.CharField(
        max_length=20, choices=AYRILMA_SEBEBI_CHOICES, verbose_name="Ayrılma Sebebi"
    )
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ogrenci_ayrilmalari",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    tarih = models.DateField(null=True, blank=True, verbose_name="Ayrılma Tarihi")
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")
    olusturma = models.DateTimeField(auto_now_add=True, verbose_name="Kayıt Tarihi")

    class Meta:
        db_table = "ogrenci_ayrilma"
        verbose_name = "Öğrenci Ayrılma Bilgisi"
        verbose_name_plural = "Öğrenci Ayrılma Bilgileri"
        ordering = ["-olusturma"]

    def __str__(self):
        return f"{self.ogrenci} — {self.get_sebep_display()}"
