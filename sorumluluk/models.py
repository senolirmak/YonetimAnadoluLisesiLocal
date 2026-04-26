from django.db import models


SALON_CHOICES = [
    ("Sorumluluk1", "Mazeret 1"),
    ("Sorumluluk2", "Mazeret 2"),
    ("Sorumluluk3", "Mazeret 3"),
]
SALON_SAYISI     = 3
SALON_KAPASITESI = 30

DONEM_TURU_CHOICES = [
    ("EYLUL",   "Eylül Dönemi"),
    ("SUBAT",   "Şubat Dönemi"),
    ("HAZIRAN", "Haziran Dönemi"),
]

SINAV_TURU_CHOICES = [("", "Normal"), ("Yazili", "Yazılı"), ("Uygulama", "Uygulama")]


class SorumluSinav(models.Model):
    """Sorumluluk sınavı planı."""
    sinav_adi        = models.CharField(max_length=200, verbose_name="Sınav Adı")
    aciklama         = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")
    egitim_yili      = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="sorumluluk_sinavlari",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    donem_turu       = models.CharField(
        max_length=10,
        choices=DONEM_TURU_CHOICES,
        default="HAZIRAN",
        verbose_name="Dönem",
    )
    olusturma_tarihi = models.DateTimeField(auto_now_add=True)
    onaylandi        = models.BooleanField(default=False, verbose_name="Onaylandı")
    onay_tarihi      = models.DateTimeField(null=True, blank=True, verbose_name="Onay Tarihi")

    class Meta:
        ordering = ["-olusturma_tarihi"]
        verbose_name = "Sorumluluk Sınavı"
        verbose_name_plural = "Sorumluluk Sınavları"

    def __str__(self):
        egitim = str(self.egitim_yili) if self.egitim_yili_id else ""
        donem  = self.get_donem_turu_display()
        return f"{self.sinav_adi} ({egitim} {donem})".strip()


class SorumluSinavParametre(models.Model):
    """Takvim algoritmasının parametreleri — ortaksinav_engine CONFIG yapısına paralel."""
    sinav = models.OneToOneField(
        SorumluSinav, on_delete=models.CASCADE,
        related_name="parametreler", verbose_name="Sınav",
    )
    baslangic_tarihi      = models.DateField(verbose_name="Başlangıç Tarihi")
    oturum_saatleri       = models.JSONField(
        default=list, verbose_name="Oturum Saatleri",
        help_text='Örn: ["10:00-10:40","11:00-11:40"]',
    )
    max_gunluk_sinav      = models.PositiveSmallIntegerField(default=2, verbose_name="Günlük Maks. Sınav")
    slot_max_ders         = models.PositiveSmallIntegerField(default=6, verbose_name="Oturumda Maks. Ders")
    tatil_tarihleri       = models.JSONField(
        default=list, verbose_name="Tatil Tarihleri",
        help_text="GG.AA.YYYY formatında tarih listesi",
    )
    hafta_sonu_haric      = models.BooleanField(default=True, verbose_name="Hafta Sonlarını Atla")
    cift_oturumlu_dersler = models.JSONField(
        default=list, verbose_name="Çift Oturumlu Dersler",
        help_text="SorumluDersHavuzu ID listesi",
    )
    max_iter              = models.PositiveSmallIntegerField(default=500, verbose_name="Maks. İterasyon")

    class Meta:
        verbose_name = "Sınav Parametresi"
        verbose_name_plural = "Sınav Parametreleri"

    def __str__(self):
        return f"{self.sinav} — Parametreler"


class SorumluOgrenci(models.Model):
    """e-Okul'dan aktarılan, sorumlu dersi olan öğrenci kaydı (sınava özgü)."""
    sinav      = models.ForeignKey(
        SorumluSinav, on_delete=models.CASCADE,
        related_name="ogrenciler", verbose_name="Sınav",
    )
    okulno     = models.CharField(max_length=20, verbose_name="Okul No")
    adi_soyadi = models.CharField(max_length=200, verbose_name="Adı Soyadı")
    sinif      = models.PositiveSmallIntegerField(verbose_name="Mevcut Sınıf")
    sube       = models.CharField(max_length=4, verbose_name="Şube")
    aktif      = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        ordering = ["sinif", "sube", "adi_soyadi"]
        unique_together = [("sinav", "okulno")]
        verbose_name = "Sorumlu Öğrenci"
        verbose_name_plural = "Sorumlu Öğrenciler"

    def __str__(self):
        return f"{self.adi_soyadi} ({self.sinif}/{self.sube})"

    @property
    def sinifsube(self):
        return f"{self.sinif}/{self.sube}"


class SorumluDersHavuzu(models.Model):
    """Sınavda sorumlu olunan tekil dersler (sınıf seviyesiyle birlikte)."""
    sinav        = models.ForeignKey(
        SorumluSinav, on_delete=models.CASCADE,
        related_name="ders_havuzu", verbose_name="Sınav",
    )
    ders_adi     = models.CharField(max_length=200, verbose_name="Ders Adı")
    onceki_sinif = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Sınıf Seviyesi",
    )

    class Meta:
        ordering = ["onceki_sinif", "ders_adi"]
        unique_together = [("sinav", "ders_adi", "onceki_sinif")]
        verbose_name = "Sorumlu Ders Havuzu"
        verbose_name_plural = "Sorumlu Ders Havuzu"

    def __str__(self):
        return f"{self.ders_adi} ({self.onceki_sinif}. Sınıf)"


class SorumluDers(models.Model):
    """Öğrencinin sorumlu olduğu ders kaydı."""
    ogrenci     = models.ForeignKey(
        SorumluOgrenci, on_delete=models.CASCADE,
        related_name="dersler", verbose_name="Öğrenci",
    )
    havuz_dersi = models.ForeignKey(
        SorumluDersHavuzu, on_delete=models.CASCADE,
        related_name="sorumlu_ogrenciler", verbose_name="Havuz Dersi",
    )

    class Meta:
        ordering = ["havuz_dersi__ders_adi"]
        unique_together = [("ogrenci", "havuz_dersi")]
        verbose_name = "Sorumlu Ders"
        verbose_name_plural = "Sorumlu Dersler"

    def __str__(self):
        return f"{self.ogrenci} – {self.havuz_dersi.ders_adi} ({self.havuz_dersi.onceki_sinif}. Sınıf)"

    @property
    def ders_adi(self):
        return self.havuz_dersi.ders_adi

    @property
    def onceki_sinif(self):
        return self.havuz_dersi.onceki_sinif


class SorumluTakvim(models.Model):
    """Üretilen takvimin düz kaydı: her satır bir oturumdaki bir dersi temsil eder.

    SorumluGun + SorumluOturum + SorumluOturumDers hiyerarşisinin sadeleştirilmiş hali.
    ortaksinav_engine'deki Takvim modeliyle aynı yapı anlayışındadır.
    """
    sinav          = models.ForeignKey(
        SorumluSinav, on_delete=models.CASCADE,
        related_name="takvim", verbose_name="Sınav",
    )
    tarih          = models.DateField(verbose_name="Tarih")
    oturum_no      = models.PositiveSmallIntegerField(verbose_name="Oturum No")
    saat_baslangic = models.TimeField(verbose_name="Başlangıç")
    saat_bitis     = models.TimeField(verbose_name="Bitiş")
    sinav_turu     = models.CharField(
        max_length=20, choices=SINAV_TURU_CHOICES,
        default="", blank=True, verbose_name="Tür",
    )
    ders_adi       = models.CharField(max_length=200, verbose_name="Ders Adı")

    class Meta:
        ordering = ["tarih", "oturum_no", "ders_adi"]
        unique_together = [("sinav", "tarih", "oturum_no", "ders_adi")]
        verbose_name = "Takvim Kaydı"
        verbose_name_plural = "Takvim Kayıtları"

    def __str__(self):
        return (
            f"{self.tarih:%d.%m.%Y} Ot.{self.oturum_no} "
            f"{self.saat_baslangic:%H:%M} – {self.ders_adi}"
        )


class SorumluOturmaPlani(models.Model):
    """Öğrencilerin salon ve sıra numarasına göre oturma düzeni."""
    sinav          = models.ForeignKey(
        SorumluSinav, on_delete=models.CASCADE,
        related_name="oturma_plani", verbose_name="Sınav",
    )
    tarih          = models.DateField(verbose_name="Tarih")
    oturum_no      = models.PositiveSmallIntegerField(verbose_name="Oturum No")
    saat_baslangic = models.TimeField(verbose_name="Başlangıç")
    saat_bitis     = models.TimeField(verbose_name="Bitiş")
    salon          = models.CharField(max_length=20, choices=SALON_CHOICES, verbose_name="Salon")
    sira_no        = models.PositiveSmallIntegerField(verbose_name="Sıra No")
    okulno         = models.CharField(max_length=20, verbose_name="Okul No")
    adi_soyadi     = models.CharField(max_length=200, verbose_name="Adı Soyadı")
    sinifsube      = models.CharField(max_length=10, verbose_name="Sınıf/Şube")
    ders_adi       = models.CharField(max_length=200, verbose_name="Ders")
    onceki_sinif   = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Sınıf")

    class Meta:
        ordering = ["tarih", "oturum_no", "salon", "sira_no"]
        unique_together = [("sinav", "tarih", "oturum_no", "salon", "sira_no")]
        verbose_name = "Oturma Planı Kaydı"
        verbose_name_plural = "Oturma Planı"

    def __str__(self):
        return (
            f"{self.tarih:%d.%m.%Y} Ot.{self.oturum_no} "
            f"– {self.salon}/{self.sira_no} – {self.adi_soyadi}"
        )