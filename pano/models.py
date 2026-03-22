from django.db import models

# Create your models here.
from django.utils import timezone

WORKING_DAYS = [1, 2, 3, 4, 5, 6]  # Pazartesi..Cuma (istersen 6'yı da ekle)


class Duyuru(models.Model):
    baslik = models.CharField("Başlık", max_length=120, blank=True)
    metin = models.TextField("Duyuru Metni")
    aktif = models.BooleanField("Aktif", default=True)

    # Zaman aralığı (boşsa sınırsız)
    baslangic = models.DateTimeField("Başlangıç", null=True, blank=True)
    bitis = models.DateTimeField("Bitiş", null=True, blank=True)

    # Kayar bant sırası
    sira = models.PositiveIntegerField("Sıra", default=10)

    # İsteğe bağlı: emoji/etiket
    etiket = models.CharField("Etiket", max_length=32, blank=True)

    olusturma = models.DateTimeField("Oluşturma", auto_now_add=True)
    guncelleme = models.DateTimeField("Güncelleme", auto_now=True)

    class Meta:
        ordering = ["sira", "-olusturma"]
        verbose_name = "Duyuru"
        verbose_name_plural = "Duyurular"

    def __str__(self):
        return (self.baslik or self.metin[:40]).strip()

    def yayinda_mi(self, now=None) -> bool:
        """Şu anda yayında mı? (aktif + tarih aralığı kontrolü)"""
        now = now or timezone.now()
        if not self.aktif:
            return False
        if self.baslangic and now < self.baslangic:
            return False
        if self.bitis and now > self.bitis:
            return False
        return True


class DersSaati(models.Model):
    class Gun(models.IntegerChoices):
        PAZARTESI = 1, "Pazartesi"
        SALI = 2, "Salı"
        CARSAMBA = 3, "Çarşamba"
        PERSEMBE = 4, "Perşembe"
        CUMA = 5, "Cuma"
        CUMARTESI = 6, "Cumartesi"
        PAZAR = 7, "Pazar"

    gun = models.IntegerField("Gün", choices=Gun.choices)
    ders_no = models.PositiveSmallIntegerField("Ders No")
    baslangic = models.TimeField("Başlangıç Saati")
    sure_dk = models.PositiveSmallIntegerField("Süre (dk)", default=40)

    aktif = models.BooleanField("Aktif", default=True)

    class Meta:
        ordering = ["gun", "ders_no"]
        unique_together = [("gun", "ders_no")]
        verbose_name = "Ders Saati"
        verbose_name_plural = "Ders Saatleri"

    def __str__(self):
        return f"{self.get_gun_display()} {self.ders_no}. Ders {self.baslangic.strftime('%H:%M')}"


class Etkinlik(models.Model):
    baslik = models.CharField("Başlık", max_length=200)
    aciklama = models.TextField("Açıklama", blank=True)

    baslangic = models.DateTimeField("Başlangıç")
    bitis = models.DateTimeField("Bitiş", null=True, blank=True)

    yer = models.CharField("Yer", max_length=200, blank=True)
    aktif = models.BooleanField("Aktif", default=True)
    afis = models.ImageField("Afiş", upload_to="afisler/", null=True, blank=True)
    olusturma = models.DateTimeField("Oluşturma", auto_now_add=True)
    guncelleme = models.DateTimeField("Güncelleme", auto_now=True)

    class Meta:
        ordering = ["baslangic"]
        verbose_name = "Etkinlik"
        verbose_name_plural = "Etkinlikler"

    def __str__(self):
        return self.baslik

    def sure_metni(self):
        """
        Template'de kolay gösterim:
        - bitiş yoksa: '15:30'
        - bitiş varsa: '15:30–16:20'
        """
        b = timezone.localtime(self.baslangic)
        if self.bitis:
            e = timezone.localtime(self.bitis)
            return f"{b:%H:%M}–{e:%H:%M}"
        return f"{b:%H:%M}"

    def devam_ediyor(self):
        """Şu an devam ediyor mu?"""
        now = timezone.now()
        if self.bitis:
            return self.baslangic <= now <= self.bitis
        return False


class MedyaIcerik(models.Model):
    TUR_SECENEKLERI = [
        ("image", "Resim"),
        ("video", "Video"),
    ]

    baslik = models.CharField("Başlık", max_length=100, blank=True)
    aciklama = models.TextField("Açıklama", blank=True)
    dosya = models.FileField("Dosya", upload_to="medya_icerik/")
    tur = models.CharField("Tür", max_length=10, choices=TUR_SECENEKLERI, default="image")
    sure = models.PositiveIntegerField(
        "Süre (sn)",
        default=15,
        help_text="Resimler için gösterim süresi. Videolar kendi süresince oynar.",
    )
    sira = models.PositiveIntegerField("Sıra", default=10)
    aktif = models.BooleanField("Aktif", default=True)
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sira", "-olusturma"]
        verbose_name = "Medya İçerik"
        verbose_name_plural = "Medya İçerikleri"

    def __str__(self):
        return self.baslik or str(self.dosya.name)


class KioskAyar(models.Model):
    # saniye cinsinden
    ana_sayfa_sure = models.PositiveIntegerField(
        default=15, help_text="Ana sayfa ekranda kaç saniye kalsın?"
    )
    etkinlik_sure = models.PositiveIntegerField(
        default=15, help_text="Etkinlikler ekranda kaç saniye kalsın?"
    )

    # efekt: fade / slide (istersen artırırız)
    EFFECT_CHOICES = [
        ("fade", "Fade"),
        ("slide", "Slide"),
    ]
    efekt = models.CharField(max_length=10, choices=EFFECT_CHOICES, default="fade")

    aktif = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Kiosk Ayarı"
        verbose_name_plural = "Kiosk Ayarları"

    def __str__(self):
        return (
            f"KioskAyar (ana:{self.ana_sayfa_sure}s, etkinlik:{self.etkinlik_sure}s, {self.efekt})"
        )

    def save(self, *args, **kwargs):
        if not self.pk:
            KioskAyar.objects.update(aktif=False)
        super().save(*args, **kwargs)
