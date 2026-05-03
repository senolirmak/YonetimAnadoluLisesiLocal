from datetime import timedelta
from decimal import Decimal
from math import floor

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

GOREV_KOD_CHOICES = [
    ("mudur", "Okul Müdürü"),
    ("mudur_yardimcisi", "Müdür Yardımcısı"),
    ("brans_ogretmeni", "Öğretmen"),
    ("rehber_ogretmen", "Rehberlik"),
    ("ucretli_ogretmen", "Ücretli Öğretmen"),
]

# Personel.gorev_tipi (serbest metin) → GorevTipi.kod eşlemesi
GOREV_TIPI_ESLEME = {
    "Okul Müdürü": "mudur",
    "Müdür Yardımcısı": "mudur_yardimcisi",
    "Öğretmen": "brans_ogretmeni",
    "Rehberlik": "rehber_ogretmen",
    "Ücretli Öğretmen": "ucretli_ogretmen",
}


class GorevTipi(models.Model):
    kod = models.CharField(max_length=30, unique=True, choices=GOREV_KOD_CHOICES, verbose_name="Kod")
    ad = models.CharField(max_length=50, verbose_name="Ad")
    maas_karsiligi_haftalik = models.IntegerField(
        default=0,
        verbose_name="Maaş Karşılığı (saat/hafta)",
        help_text="Bu göreve ait haftalık ders saatinin maaşa dahil kısmı.",
    )
    hazirlik_katsayi = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0.00"),
        verbose_name="Hazırlık Katsayısı",
        help_text="0.50 → her 2 saate 1 saat ek hazırlık (ücretli öğretmen için).",
    )

    class Meta:
        verbose_name = "Görev Tipi"
        verbose_name_plural = "Görev Tipleri"
        ordering = ["ad"]

    def __str__(self):
        return f"{self.ad} ({self.maas_karsiligi_haftalik} saat/hafta)"


class Tatil(models.Model):
    ad = models.CharField(max_length=100, verbose_name="Tatil Adı")
    baslangic = models.DateField(verbose_name="Başlangıç")
    bitis = models.DateField(verbose_name="Bitiş")

    class Meta:
        verbose_name = "Tatil"
        verbose_name_plural = "Tatiller"
        ordering = ["baslangic"]

    def __str__(self):
        return f"{self.ad} ({self.baslangic:%d.%m.%Y} – {self.bitis:%d.%m.%Y})"

    @classmethod
    def donem_tatil_gun_sayisi(cls, donem_bas, donem_bit):
        """Dönem içindeki iş günü tatil sayısını döndürür (haftasonu hariç)."""
        toplam = 0
        for tatil in cls.objects.filter(baslangic__lte=donem_bit, bitis__gte=donem_bas):
            start = max(tatil.baslangic, donem_bas)
            end = min(tatil.bitis, donem_bit)
            for i in range((end - start).days + 1):
                d = start + timedelta(days=i)
                if d.weekday() < 5:
                    toplam += 1
        return toplam


class EkDersDonemi(models.Model):
    ad = models.CharField(max_length=100, verbose_name="Dönem Adı")
    baslangic_tarihi = models.DateField(verbose_name="Başlangıç Tarihi")
    bitis_tarihi = models.DateField(verbose_name="Bitiş Tarihi")
    hafta_sayisi = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Hafta Sayısı",
        help_text="Boş bırakılırsa tatil günleri düşülerek otomatik hesaplanır.",
    )
    kapandi = models.BooleanField(default=False, verbose_name="Kapalı")
    olusturan = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Oluşturan",
    )
    olusturma_tarihi = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ek Ders Dönemi"
        verbose_name_plural = "Ek Ders Dönemleri"
        ordering = ["-baslangic_tarihi"]

    def __str__(self):
        return self.ad

    def hesapla_hafta_sayisi(self):
        bas = self.baslangic_tarihi
        bit = self.bitis_tarihi
        toplam_gun = (bit - bas).days + 1
        haftasonu = sum(
            1 for i in range(toplam_gun)
            if (bas + timedelta(days=i)).weekday() >= 5
        )
        tatil_gun = Tatil.donem_tatil_gun_sayisi(bas, bit)
        calisma_gun = toplam_gun - haftasonu - tatil_gun
        return Decimal(calisma_gun) / Decimal(5)

    def save(self, *args, **kwargs):
        if not self.hafta_sayisi:
            self.hafta_sayisi = self.hesapla_hafta_sayisi()
        super().save(*args, **kwargs)


class OgretmenEkDers(models.Model):
    donem = models.ForeignKey(
        EkDersDonemi, on_delete=models.CASCADE, related_name="kayitlar",
    )
    personel = models.ForeignKey(
        "okul.Personel", on_delete=models.CASCADE, related_name="ekders_kayitlari",
    )
    gorev_tipi = models.ForeignKey(GorevTipi, on_delete=models.PROTECT)
    hafta_baslangic = models.DateField(verbose_name="Hafta Başlangıcı (Pazartesi)")

    # Günlük ders yükü — REHBERLİK VE YÖNLENDİRME hariç
    pazartesi = models.IntegerField(default=0)
    sali = models.IntegerField(default=0)
    carsamba = models.IntegerField(default=0)
    persembe = models.IntegerField(default=0)
    cuma = models.IntegerField(default=0)
    cumartesi = models.IntegerField(default=0)
    pazar = models.IntegerField(default=0)

    nobet_sayisi = models.IntegerField(default=0, verbose_name="Nöbet Sayısı")
    diger_zorunlu_saat = models.IntegerField(default=0, verbose_name="Diğer Zorunlu Saat")
    notlar = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Öğretmen Ek Ders (Haftalık)"
        verbose_name_plural = "Öğretmen Ek Ders Kayıtları"
        unique_together = ("donem", "personel", "hafta_baslangic")
        ordering = ["hafta_baslangic", "personel__adi_soyadi"]

    def __str__(self):
        return f"{self.personel} – {self.hafta_baslangic:%d.%m.%Y}"

    @property
    def haftalik_ders_saati(self):
        return (
            self.pazartesi + self.sali + self.carsamba
            + self.persembe + self.cuma + self.cumartesi + self.pazar
        )

    @property
    def nobet_saati(self):
        return self.nobet_sayisi * 3


class EkDersOnay(models.Model):
    donem = models.OneToOneField(
        EkDersDonemi, on_delete=models.CASCADE, related_name="onay",
    )
    onaylayan = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, verbose_name="Onaylayan",
    )
    onay_tarihi = models.DateTimeField(auto_now_add=True)
    notlar = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Ek Ders Onayı"
        verbose_name_plural = "Ek Ders Onayları"

    def __str__(self):
        return f"{self.donem} – {self.onaylayan}"
