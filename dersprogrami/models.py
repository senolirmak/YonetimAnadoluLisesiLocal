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


class DersProgramiQuerySet(models.QuerySet):
    def aktif(self):
        """Arşivlenmemiş (bkz. senesonu.services.gecis_uygula) kayıtları döner —
        aktif ders programı tarihi tanımlıysa o tarihe, tanımlı değilse
        arşivlenmemiş kayıtların en güncel tarihine daralır."""
        from okul.utils import get_aktif_dp_tarihi

        guncel = self.filter(arsivlendi=False)
        tarih = get_aktif_dp_tarihi()
        return guncel.filter(uygulama_tarihi=tarih) if tarih else guncel


class DersProgrami(models.Model):
    objects = DersProgramiQuerySet.as_manager()
    gun = models.CharField(max_length=10, choices=GUNLER)
    ders = models.ForeignKey(
        "okul.DersHavuzu",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dersprogrami",
        verbose_name="Ders",
    )
    sinif_sube = models.ForeignKey(
        "okul.SinifSube",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dersprogrami",
        verbose_name="Sınıf/Şube",
    )
    ders_saati = models.ForeignKey(
        "okul.DersSaatleri",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dersprogrami",
        verbose_name="Ders Saati",
    )
    uygulama_tarihi = models.DateField(default=timezone.now)
    ogretmen = models.ForeignKey(
        "okul.Personel", on_delete=models.CASCADE, related_name="dersprogrami"
    )
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ders_programlari",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    donem = models.ForeignKey(
        "okul.OkulDonem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ders_programlari",
        verbose_name="Dönem",
    )
    arsivlendi = models.BooleanField(
        default=False,
        verbose_name="Arşivlendi",
        help_text=(
            "Sene Sonu Geçişi uygulandığında geçmiş eğitim-öğretim yılına ait ders "
            "programı yüklemeleri otomatik olarak arşivlenir; arşivlenen kayıtlar "
            "artık 'aktif' ders programı olarak gösterilmez, yalnızca Ders Programı "
            "Listesi (arşiv) sayfasından eğitim yılı/dönem seçilerek görüntülenebilir."
        ),
    )

    class Meta:
        db_table = "nobet_dersprogrami"
        verbose_name = "Ders Programı"
        verbose_name_plural = "Haftalık Ders Programı"

    # ------------------------------------------------------------------
    # Backward-compat properties — ORM sorguları için .derssaati_no kullanın
    # ------------------------------------------------------------------

    @property
    def giris_saat(self):
        return self.ders_saati.derssaati_baslangic if self.ders_saati else None

    @property
    def cikis_saat(self):
        return self.ders_saati.derssaati_bitis if self.ders_saati else None

    @property
    def ders_saati_adi(self):
        return self.ders_saati.ders_adi if self.ders_saati else ""

    @property
    def ders_adi(self):
        return self.ders.ders_adi if self.ders else ""


class FetYayini(models.Model):
    """FET bilgisayarından (timetableokul) gönderilen, kabul edilmiş ders programı paketi.

    Paket gelen kutusunda bekler; ders programı ve nöbet listesine ancak bir üst yönetici
    "İçeri al" dediğinde, `uygulama_tarihi` ile YENİ sürümler olarak yazılır
    (bkz. `dersprogrami/services/fet_yayin.py`). Aktif yapmak ayrı bir onaydır.
    """

    DURUM_BEKLIYOR = "bekliyor"
    DURUM_ICE_ALINDI = "ice_alindi"
    DURUM_REDDEDILDI = "reddedildi"
    DURUM_CHOICES = (
        (DURUM_BEKLIYOR, "Bekliyor"),
        (DURUM_ICE_ALINDI, "İçeri alındı"),
        (DURUM_REDDEDILDI, "Reddedildi"),
    )

    alinma = models.DateTimeField(auto_now_add=True, verbose_name="Alınma Zamanı")
    kaynak = models.CharField(max_length=100, blank=True, verbose_name="Gönderen")
    cozum = models.CharField(max_length=300, verbose_name="FET Çözümü")
    uygulama_tarihi = models.DateField(verbose_name="Uygulama Tarihi")
    okul_adi = models.CharField(max_length=200, blank=True, verbose_name="Okul Adı")
    egitim_yili = models.CharField(max_length=9, blank=True, verbose_name="Eğitim-Öğretim Yılı")
    donem = models.CharField(max_length=20, blank=True, verbose_name="Dönem")
    fet_icerik = models.BinaryField(verbose_name="FET Çözüm Dosyası")
    nobet = models.JSONField(default=list, blank=True, verbose_name="Nöbet Listesi")
    ozet = models.JSONField(default=dict, blank=True, verbose_name="Özet")
    imza = models.CharField(max_length=64, unique=True, verbose_name="İçerik İmzası (SHA-256)")
    durum = models.CharField(max_length=12, choices=DURUM_CHOICES, default=DURUM_BEKLIYOR,
                             verbose_name="Durum")
    isleyen = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="+", verbose_name="İşleyen")
    islem_zamani = models.DateTimeField(null=True, blank=True, verbose_name="İşlem Zamanı")
    notlar = models.TextField(blank=True, verbose_name="Notlar")

    class Meta:
        db_table = "dersprogrami_fet_yayini"
        ordering = ["-alinma"]
        verbose_name = "Gelen FET Programı"
        verbose_name_plural = "Gelen FET Programları"

    def __str__(self):
        return f"{self.cozum} ({self.uygulama_tarihi:%d.%m.%Y})"
