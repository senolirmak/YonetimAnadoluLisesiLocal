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


class NobetYerleri(models.Model):
    """
    Nöbet listesi verisinden elde edilen tekil nöbet yeri havuzu.

    Import sırasında NobetGorevi.nobet_yeri stringleri buraya sync edilir.
    Aktif=False yapılan yerler otomatik dağıtım dışında tutulabilir.
    """

    ad = models.CharField(max_length=100, unique=True, verbose_name="Nöbet Yeri")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        db_table = "nobet_yerleri"
        ordering = ["ad"]
        verbose_name = "Nöbet Yeri"
        verbose_name_plural = "Nöbet Yerleri"

    def __str__(self):
        return self.ad


# SinifSube → okul app'ine taşındı. Backward-compat:
from okul.models import SinifSube  # noqa: F401, E402

# NobetPersonel → okul app'ine Personel adıyla taşındı. Backward-compat:
from okul.models import Personel  # noqa: F401, E402
from okul.models import Personel as NobetPersonel  # noqa: F401, E402


class NobetOgretmen(models.Model):
    personel = models.OneToOneField(
        "okul.Personel", on_delete=models.CASCADE, related_name="ogretmen"
    )
    uygulama_tarihi = models.DateField(default=timezone.now)

    class Meta:
        db_table = "nobet_ogretmen"
        verbose_name = "Öğretmenler"
        verbose_name_plural = "Ders Görevi Olan Öğretmenler"

    def __str__(self):
        return self.personel.adi_soyadi


class NobetGoreviQuerySet(models.QuerySet):
    def aktif(self):
        from okul.utils import get_aktif_nobet_tarihi

        tarih = get_aktif_nobet_tarihi()
        return self.filter(uygulama_tarihi=tarih) if tarih else self


class NobetGorevi(models.Model):
    objects = NobetGoreviQuerySet.as_manager()

    nobet_gun = models.CharField(max_length=10, choices=GUNLER)
    nobet_yeri = models.ForeignKey(
        "NobetYerleri",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gorevler",
        verbose_name="Nöbet Yeri",
    )
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


# OkulBilgi, OkulDonem, EgitimOgretimYili → okul app'ine taşındı.
# Mevcut import'ların kırılmaması için backward-compat takma adlar:
from okul.models import EgitimOgretimYili, OkulBilgi, OkulDonem  # noqa: F401, E402


MAZERET_SALON_CHOICES = [
    ("Mazeret1", "Mazeret1"),
    ("Mazeret2", "Mazeret2"),
]
MAZERET_DERSLER = [3, 4, 5, 6]


class MazeretSalonGorevi(models.Model):
    """
    Mazeret1 / Mazeret2 salonları için günlük ders bazında nöbetçi ataması.
    Salon o gün açık değilse kayıt oluşturulmaz.
    """

    tarih = models.DateField(verbose_name="Tarih")
    salon = models.CharField(
        max_length=20, choices=MAZERET_SALON_CHOICES, verbose_name="Salon"
    )
    saat = models.IntegerField(verbose_name="Ders Saati")  # 3, 4, 5, 6
    ogretmen = models.ForeignKey(
        NobetOgretmen,
        on_delete=models.CASCADE,
        related_name="mazeret_gorevleri",
        verbose_name="Görevli Nöbetçi",
    )
    kayit_zamani = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nobet_mazeret_salon_gorevi"
        unique_together = ("tarih", "salon", "saat")
        ordering = ["tarih", "salon", "saat"]
        verbose_name = "Mazeret Salon Görevi"
        verbose_name_plural = "Mazeret Salon Görevleri"

    def __str__(self):
        return f"{self.tarih} – {self.salon} – {self.saat}. Ders – {self.ogretmen}"


class VeriYukleme(models.Model):
    """Admin panelinde veri yükleme arayüzü için kullanılan proxy model."""

    class Meta:
        managed = False  # Veritabanında tablo oluşturmaz
        verbose_name = "Veri Yükleme ve Aktarım"
        verbose_name_plural = "Veri Yükleme ve Aktarım"
