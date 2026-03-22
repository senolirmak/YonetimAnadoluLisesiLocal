from django.contrib.auth.models import User
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


# Create your models here.
class SinifSube(models.Model):
    sinif = models.IntegerField()
    sube = models.CharField(max_length=2)

    class Meta:
        unique_together = ("sinif", "sube")
        verbose_name = "Sınıf Şube"
        verbose_name_plural = "Sınıf ve Şubeler"

    def __str__(self):
        return f"{self.sinif}/{self.sube}"

    @property
    def sinif_sube(self):
        return f"{self.sinif}/{self.sube}"


class NobetPersonel(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personel",
        verbose_name="Kullanıcı",
    )
    kimlikno = models.CharField(max_length=11, unique=True)
    adi_soyadi = models.CharField(max_length=100, unique=True)
    brans = models.CharField(max_length=50)
    CINSIYET_CHOICES = (
        (True, "Erkek"),
        (False, "Kadın"),
    )
    cinsiyet = models.BooleanField(default=True, choices=CINSIYET_CHOICES)
    nobeti_var = models.BooleanField(default=True)
    gorev_tipi = models.CharField(max_length=50, blank=True, null=True)
    sabit_nobet = models.BooleanField(default=False)

    class Meta:
        db_table = "nobet_personel"
        verbose_name = "Personel"
        verbose_name_plural = "Personel Listesi"

    def __str__(self):
        return self.adi_soyadi


class NobetOgretmen(models.Model):
    personel = models.OneToOneField(
        NobetPersonel, on_delete=models.CASCADE, related_name="ogretmen"
    )
    uygulama_tarihi = models.DateField(default=timezone.now)

    class Meta:
        db_table = "nobet_ogretmen"
        verbose_name = "Öğretmenler"
        verbose_name_plural = "Ders Görevi Olan Öğretmenler"

    def __str__(self):
        return self.personel.adi_soyadi


class NobetGorevi(models.Model):
    nobet_gun = models.CharField(max_length=10, choices=GUNLER)
    nobet_yeri = models.CharField(max_length=100)
    uygulama_tarihi = models.DateField(default=timezone.now)
    ogretmen = models.ForeignKey(NobetOgretmen, on_delete=models.CASCADE, related_name="nobetler")

    class Meta:
        db_table = "nobet_gorevi"
        verbose_name = "Nöbet Görevi"
        verbose_name_plural = "Haftalık Nöbet Görevleri"


class NobetGecmisi(models.Model):
    saat = models.IntegerField(null=True, blank=True)
    sinif = models.CharField(max_length=50, null=True, blank=True)
    devamsiz = models.IntegerField(null=True, blank=True)
    tarih = models.DateTimeField(default=timezone.now)
    atandi = models.IntegerField(default=1)
    ogretmen = models.ForeignKey(NobetOgretmen, on_delete=models.CASCADE, related_name="gecmis")

    class Meta:
        db_table = "nobet_gecmis"


class NobetAtanamayan(models.Model):
    saat = models.IntegerField(null=True, blank=True)
    sinif = models.CharField(max_length=50, null=True, blank=True)
    tarih = models.DateTimeField(default=timezone.now)
    atandi = models.IntegerField(default=0)
    ogretmen = models.ForeignKey(NobetOgretmen, on_delete=models.CASCADE, related_name="atanamayan")

    class Meta:
        db_table = "nobet_atanamayan"


class NobetIstatistik(models.Model):
    toplam_nobet = models.IntegerField(default=0)
    atanmayan_nobet = models.IntegerField(default=0)
    haftalik_ortalama = models.FloatField(default=0.0)
    hafta_sayisi = models.IntegerField(default=0)
    son_nobet_tarihi = models.DateTimeField(null=True, blank=True)
    agirlikli_puan = models.FloatField(default=1.0)
    son_nobet_yeri = models.CharField(max_length=100, null=True, blank=True)
    ogretmen = models.OneToOneField(
        NobetOgretmen, on_delete=models.CASCADE, related_name="istatistikler"
    )

    class Meta:
        db_table = "nobet_istatistik"


class NobetDegisimKaydi(models.Model):
    uygulama_tarihi = models.DateField(default=timezone.now)
    uygulama_baslangic = models.DateTimeField()
    uygulama_bitis = models.DateTimeField()
    aciklama = models.CharField(max_length=200, default="Haftalık nöbet rotasyonu uygulandı")

    class Meta:
        db_table = "nobet_degisim_kaydi"


class GunlukNobetCizelgesi(models.Model):
    tarih = models.DateField(default=timezone.now)
    ogretmen = models.ForeignKey(
        NobetOgretmen, on_delete=models.CASCADE, related_name="gunluk_nobetler"
    )
    nobet_yeri = models.CharField(max_length=100)

    class Meta:
        db_table = "gunluk_nobet_cizelgesi"
        unique_together = ("tarih", "ogretmen")
        verbose_name = "Günlük Nöbet Çizelgesi"
        verbose_name_plural = "Günlük Nöbet Çizelgeleri"


class OkulBilgi(models.Model):
    okul_kodu = models.CharField(max_length=20, blank=True, verbose_name="Okul Kodu")
    okul_adi = models.CharField(max_length=200, blank=True, verbose_name="Okul Adı")
    okul_muduru = models.CharField(max_length=100, blank=True, verbose_name="Okul Müdürü")

    class Meta:
        db_table = "okul_bilgi"
        verbose_name = "Okul Bilgisi"
        verbose_name_plural = "Okul Bilgileri"

    def __str__(self):
        return self.okul_adi or "Okul Bilgisi"


class VeriYukleme(models.Model):
    """Admin panelinde veri yükleme arayüzü için kullanılan proxy model."""

    class Meta:
        managed = False  # Veritabanında tablo oluşturmaz
        verbose_name = "Veri Yükleme ve Aktarım"
        verbose_name_plural = "Veri Yükleme ve Aktarım"
