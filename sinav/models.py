from django.db import models
from django.db.models import Value
from django.db.models.functions import Concat
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone


# ---------------------------------------------------------------------------
# OkulBilgileri — nobet.OkulBilgi için geriye dönük uyumluluk takma adı
# ---------------------------------------------------------------------------
def _get_okul_bilgileri():
    from nobet.models import OkulBilgi
    return OkulBilgi.get()

OkulBilgileri = None  # views.py import'larını kırmamak için; gerçek sınıf nobet.OkulBilgi


class SinavBilgisi(models.Model):
    DONEM_CHOICES = [
        ("1. Donem", "1. Dönem"),
        ("2. Donem", "2. Dönem"),
    ]
    SINAV_ADI_CHOICES = [
        ("1. Ortak Sinav", "1. Ortak Sınav"),
        ("2. Ortak Sinav", "2. Ortak Sınav"),
    ]

    egitim_ogretim_yili = models.CharField(max_length=20, verbose_name="Eğitim-Öğretim Yılı")
    donem = models.CharField(max_length=20, choices=DONEM_CHOICES, verbose_name="Dönem")
    sinav_adi = models.CharField(max_length=100, choices=SINAV_ADI_CHOICES, verbose_name="Sınav Adı")
    sinav_baslangic_tarihi = models.DateField(verbose_name="Sınav Başlangıç Tarihi")
    eokul_veri_tarihi = models.DateField(verbose_name="e-Okul Veri Tarihi")
    kurum = models.ForeignKey(
        "nobet.OkulBilgi", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sinavlar",
        verbose_name="Kurum",
    )
    egitim_yili_fk = models.ForeignKey(
        "nobet.EgitimOgretimYili", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sinavlar",
        verbose_name="Eğitim-Öğretim Yılı (Bağlantı)",
    )
    donem_fk = models.ForeignKey(
        "nobet.OkulDonem", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sinavlar",
        verbose_name="Dönem (Bağlantı)",
    )
    aktif = models.BooleanField(default=False)
    olusturulma_zamani = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-olusturulma_zamani"]

    def __str__(self):
        return f"{self.egitim_ogretim_yili} – {self.get_donem_display()} – {self.get_sinav_adi_display()}"

    def aktif_yap(self):
        SinavBilgisi.objects.all().update(aktif=False)
        self.aktif = True
        self.save()


# Ogrenci modeli kaldırıldı — ogrenci.Ogrenci kullanılmaktadır.


class DersHavuzu(models.Model):
    """e-Okul haftalik ders programindan elde edilen tekil ders adi havuzu."""
    ders_adi = models.CharField(max_length=200, unique=True)

    class Meta:
        ordering = ["ders_adi"]

    def __str__(self):
        return self.ders_adi


# DersProgram modeli kaldırıldı — dersprogrami.NobetDersProgrami kullanılmaktadır.



class SubeDers(models.Model):
    ders =  models.ForeignKey(
        "DersHavuzu", on_delete=models.CASCADE,
        related_name="sube_dersler", null=True,
    )
    seviye = models.IntegerField()
    sube = models.ForeignKey(
        "nobet.SinifSube", on_delete=models.CASCADE,
        related_name="sinav_sube_dersler", null=True,
    )
    class Meta:
        ordering = ["seviye", "sube", "ders"]
        unique_together = [("ders", "seviye", "sube")]

    def __str__(self):
        return f"{self.sube} – {self.ders}"


class Takvim(models.Model):
    sinav = models.ForeignKey(
        "SinavBilgisi", on_delete=models.CASCADE,
        null=True, blank=True, related_name="takvimler",
    )
    uretim = models.ForeignKey(
        "TakvimUretim", on_delete=models.CASCADE,
        null=True, blank=True, related_name="takvimler_uretim",
    )
    tarih = models.DateField()
    saat = models.CharField(max_length=10)
    oturum = models.IntegerField()
    ders = models.ForeignKey(
        "DersHavuzu", on_delete=models.CASCADE,
        related_name="takvimler", null=True,
    )
    ders_adi = models.CharField(max_length=200, blank=True, default="")
    subeler = models.TextField()

    class Meta:
        ordering = ["tarih", "saat", "ders"]

    def __str__(self):
        return f"{self.tarih} {self.saat} – {self.ders}"


class OturmaPlani(models.Model):
    sinav = models.ForeignKey(
        "SinavBilgisi", on_delete=models.CASCADE,
        null=True, blank=True, related_name="oturma_planlari",
    )
    uretim = models.ForeignKey(
        "TakvimUretim", on_delete=models.CASCADE,
        null=True, blank=True, related_name="oturma_planlari",
    )
    tarih = models.DateField()
    saat = models.CharField(max_length=10)
    oturum = models.IntegerField()
    salon = models.CharField(max_length=50)
    sira_no = models.IntegerField()
    okulno = models.CharField(max_length=20)
    sinifsube = models.CharField(max_length=10)
    adi_soyadi = models.CharField(max_length=200)
    ders_adi = models.CharField(max_length=200)

    class Meta:
        ordering = ["tarih", "saat", "salon", "sira_no"]

    def __str__(self):
        return f"{self.tarih} {self.saat} {self.salon} – {self.sira_no}: {self.adi_soyadi}"


class OturmaUretim(models.Model):
    """
    Her oturum için oturma planı üretimini kayıt altına alır.
    takvim_uretim + tarih + saat + oturum kombinasyonu unique'tir.
    PDF linkleri bu modelin pk'sı üzerinden doğru üretime bağlanır.
    """
    takvim_uretim = models.ForeignKey(
        "TakvimUretim", on_delete=models.CASCADE,
        related_name="oturma_uretimler",
    )
    tarih = models.DateField()
    saat = models.CharField(max_length=10)
    oturum = models.IntegerField()
    uretim_tarihi = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uretim_tarihi"]
        unique_together = [("takvim_uretim", "tarih", "saat", "oturum")]

    def __str__(self):
        return f"{self.takvim_uretim} – {self.tarih} {self.saat} Ot.{self.oturum}"


class DersAyarlariJSON(models.Model):
    """
    Aktif sınava ait tüm ders ayarlarını tek bir JSON alanında tutar.
    Yapilmayacak dersler, çift oturumlu dersler, sabit sınavlar,
    çakışma grupları ve aynı slot eşlemelerini içerir.
    """
    sinav = models.OneToOneField(
        SinavBilgisi, on_delete=models.CASCADE,
        related_name="ders_ayarlari_json",
    )
    veri = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Ders Ayarları ({self.sinav})"


class DisVeri(models.Model):
    """
    Her e-Okul dosya yüklemesini kayıt altına alır.
    Aynı sinav + etiket için önceki kayıtla gecerlilik_tarihi karşılaştırılarak
    yüklemenin yeni veri mi yoksa güncelleme mi olduğu tespit edilir.
    """
    DOSYA_ETIKET_CHOICES = [
        ("ogrenci",          "Öğrenci Listesi"),
        ("haftalik_program", "Haftalık Ders Programı"),
    ]

    sinav             = models.ForeignKey(
        "SinavBilgisi", on_delete=models.CASCADE,
        null=True, blank=True, related_name="dis_veriler",
        verbose_name="Sınav",
    )
    dosya_etiketi     = models.CharField(max_length=20, choices=DOSYA_ETIKET_CHOICES,
                                         verbose_name="Dosya Etiketi")
    dosya             = models.FileField(
        upload_to="dis_veri/",
        null=True, blank=True,
        verbose_name="Excel Dosyası",
    )
    yukleme_tarihi    = models.DateTimeField(auto_now_add=True, verbose_name="Yükleme Tarihi")
    gecerlilik_tarihi = models.DateField(verbose_name="Geçerlilik Tarihi")

    class Meta:
        ordering = ["-yukleme_tarihi"]
        verbose_name = "Dış Veri"
        verbose_name_plural = "Dış Veriler"

    def yeni_veri_mi(self) -> bool | None:
        """
        Kaydedilmiş bu yüklemenin yeni dönem verisi mi yoksa güncelleme mi olduğunu döndürür.
        None  → ilk yükleme (bu sinav için)
        True  → yeni dönem (gecerlilik_tarihi öncekinden farklı)
        False → güncelleme (aynı gecerlilik_tarihi ile yeniden yükleme)
        """
        onceki = (
            DisVeri.objects
            .filter(sinav=self.sinav, dosya_etiketi=self.dosya_etiketi)
            .exclude(pk=self.pk)
            .order_by("-yukleme_tarihi")
            .first()
        )
        if onceki is None:
            return None
        return self.gecerlilik_tarihi != onceki.gecerlilik_tarihi

    def __str__(self):
        label = dict(self.DOSYA_ETIKET_CHOICES).get(self.dosya_etiketi, self.dosya_etiketi)
        sinav_str = str(self.sinav) if self.sinav else "–"
        return f"{sinav_str} | {label} – {self.gecerlilik_tarihi}"



class AlgoritmaParametreleri(models.Model):
    """
    Takvim (ILP) algoritma parametrelerini sınav bazında saklar.
    Her SinavBilgisi kaydı için en fazla bir kayıt olur (OneToOne).
    """
    sinav = models.OneToOneField(
        SinavBilgisi, on_delete=models.CASCADE,
        related_name="parametreler",
    )
    baslangic_tarih   = models.DateField(null=True, blank=True)
    oturum_saatleri   = models.CharField(
        max_length=200, default="08:50,10:30,12:10,13:35,14:25",
    )
    tatil_gunleri     = models.TextField(blank=True, default="")
    time_limit_phase1 = models.IntegerField(default=300)
    time_limit_phase2 = models.IntegerField(default=120)
    max_extra_days    = models.IntegerField(default=10)

    class Meta:
        verbose_name = "Algoritma Parametreleri"
        verbose_name_plural = "Algoritma Parametreleri"

    def __str__(self):
        return f"Parametreler – {self.sinav}"

    def to_session_dict(self) -> dict:
        """Session dict formatına dönüştürür (parametre_kaydet ile uyumlu)."""
        return {
            "baslangic_tarih":   str(self.baslangic_tarih) if self.baslangic_tarih else "",
            "oturum_saatleri":   self.oturum_saatleri,
            "tatil_gunleri":     self.tatil_gunleri,
            "time_limit_phase1": self.time_limit_phase1,
            "time_limit_phase2": self.time_limit_phase2,
            "max_extra_days":    self.max_extra_days,
        }




class TakvimUretim(models.Model):
    """
    Her başarılı takvim üretiminin meta verisi ve log kaydı.
    Hangi sınava ait, ne zaman üretildi, algoritma çıktısı neydi.
    aktif=True olan kayıt PDF rapor üretiminde kullanılır.
    """
    sinav = models.ForeignKey(
        SinavBilgisi, on_delete=models.CASCADE,
        null=True, blank=True, related_name="takvim_uretimler",
    )
    uretim_tarihi = models.DateTimeField(auto_now_add=True)
    log_metni = models.TextField(blank=True, default="")
    aktif = models.BooleanField(default=False, verbose_name="PDF Raporunda Kullan")
    oturma_sifirla = models.BooleanField(default=False)
    degisiklik_logu = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-uretim_tarihi"]

    def __str__(self):
        from django.utils import timezone
        local_dt = timezone.localtime(self.uretim_tarihi)
        return f"{self.sinav} – {local_dt:%d.%m.%Y %H:%M}"


# ---------------------------------------------------------------------------
# Sinyaller
# ---------------------------------------------------------------------------


@receiver(post_save, sender=TakvimUretim)
def takvim_uretim_aktif_degisti(sender, instance, update_fields, **_kwargs):
    """aktif alanı True olarak kaydedilince oturma_sifirla bayrağını koy."""
    if update_fields and "aktif" in update_fields and instance.aktif:
        sender.objects.filter(pk=instance.pk).update(oturma_sifirla=True)


@receiver(pre_save, sender=Takvim)
def takvim_satir_degisti(sender, instance, **_kwargs):
    """Takvim satırı güncellenince değişiklikleri logla; tarih/saat değişmişse
    etkilenen oturumların OturmaPlani kayıtlarını sil."""
    if instance.pk is None:
        return
    try:
        eski = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    izlenen = ["tarih", "saat", "oturum", "ders_adi", "subeler"]
    degisiklikler = [
        f"{alan}: {getattr(eski, alan)} → {getattr(instance, alan)}"
        for alan in izlenen
        if str(getattr(eski, alan)) != str(getattr(instance, alan))
    ]
    if not degisiklikler:
        return

    simdi = timezone.localtime(timezone.now())
    ders_kimlik = instance.ders_adi or f"pk={instance.pk}"
    log_satiri = (
        f"[{simdi:%d.%m.%Y %H:%M:%S}] Güncellendi – {ders_kimlik} (Takvim pk={instance.pk})\n"
        + "".join(f"  {d}\n" for d in degisiklikler)
    )

    if instance.uretim_id:
        TakvimUretim.objects.filter(pk=instance.uretim_id).update(
            degisiklik_logu=Concat("degisiklik_logu", Value(log_satiri)),
        )

        # Tarih veya saat değişmişse etkilenen oturumların üretim kayıtlarını ve planlarını sil
        tarih_degisti = str(eski.tarih) != str(instance.tarih)
        saat_degisti = str(eski.saat) != str(instance.saat)
        if tarih_degisti or saat_degisti:
            # Eski oturum: OturmaUretim + OturmaPlani sil
            OturmaUretim.objects.filter(
                takvim_uretim_id=instance.uretim_id,
                tarih=eski.tarih, saat=eski.saat, oturum=eski.oturum,
            ).delete()
            OturmaPlani.objects.filter(
                uretim_id=instance.uretim_id,
                tarih=eski.tarih, saat=eski.saat, oturum=eski.oturum,
            ).delete()
            # Yeni oturum: mevcut planlar bozulur, onları da sil
            OturmaUretim.objects.filter(
                takvim_uretim_id=instance.uretim_id,
                tarih=instance.tarih, saat=instance.saat,
            ).delete()
            OturmaPlani.objects.filter(
                uretim_id=instance.uretim_id,
                tarih=instance.tarih, saat=instance.saat,
            ).delete()
