from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

# akal-eta-yonetim 60 sn'de bir bağlanır; üç tur üst üste gelmezse tahta çevrimdışı sayılır.
CEVRIMICI_ESIK = timedelta(seconds=180)

# Teslim edilmemiş bir komut bu süreden sonra geçersizdir. Böylece kapalı bir
# tahtaya verilen "kapat" komutu, tahta ertesi gün açıldığında çalışmaz.
KOMUT_GECERLILIK = timedelta(minutes=10)


class TahtaQuerySet(models.QuerySet):
    def cevrimici(self):
        return self.filter(son_gorulme__gte=timezone.now() - CEVRIMICI_ESIK)

    def cevrimdisi(self):
        sinir = timezone.now() - CEVRIMICI_ESIK
        return self.filter(models.Q(son_gorulme__lt=sinir) | models.Q(son_gorulme__isnull=True))


class TahtaEnvanteri(models.Model):
    """MEB Lider'den alınan tahta envanteri (bkz. `tahta_envanteri_yukle` komutu).

    Lider'deki durum, dışa aktarma anındaki durumdur; canlı durum için
    akal-eta-yonetim'in bildirdiği `Tahta` kaydına bakılır. Kaydolan tahta MAC adresiyle
    buradaki satıra bağlanır.
    """

    lider_id = models.PositiveIntegerField("Lider Id", unique=True)
    mac_adresi = models.CharField("MAC", max_length=17, unique=True)
    okul_kodu = models.CharField("Okul kodu", max_length=20, blank=True)
    sube_adi = models.CharField("Şube adı", max_length=100)
    faz = models.CharField("Faz", max_length=50, blank=True)
    lider_cevrimici = models.BooleanField("Lider'de çevrimiçi", null=True, blank=True)
    lider_aktif = models.BooleanField("Lider'de aktif", null=True, blank=True)
    ip_adresi = models.GenericIPAddressField("IP adresi", null=True, blank=True)
    lider_olusturulma = models.DateTimeField("Lider'de oluşturulma", null=True, blank=True)
    lider_durum_degisim = models.DateTimeField("Durum değişim tarihi", null=True, blank=True)
    isletim_sistemi = models.CharField("İşletim sistemi", max_length=150, blank=True)
    ahenk_surumu = models.CharField("Ahenk sürümü", max_length=20, blank=True)
    marka = models.CharField("Marka", max_length=50, blank=True)
    model = models.CharField("Model", max_length=50, blank=True)
    islemci = models.CharField("İşlemci", max_length=150, blank=True)
    ram_gb = models.PositiveSmallIntegerField("RAM (GB)", null=True, blank=True)
    disk_toplam_gb = models.PositiveIntegerField("Toplam disk (GB)", null=True, blank=True)
    disk_kullanilan_gb = models.PositiveIntegerField("Kullanılan disk (GB)", null=True, blank=True)
    disk_bos_gb = models.PositiveIntegerField("Boş disk (GB)", null=True, blank=True)
    aktarim_tarihi = models.DateTimeField("Aktarım tarihi", auto_now=True)

    class Meta:
        verbose_name = "Tahta envanteri (MEB Lider)"
        verbose_name_plural = "Tahta envanteri (MEB Lider)"
        ordering = ["sube_adi"]

    def __str__(self):
        return f"{self.sube_adi} ({self.mac_adresi})"


class Tahta(models.Model):
    AHENK_CALISIYOR = "calisiyor"
    AHENK_DURMUS = "durmus"
    AHENK_YOK = "yok"
    AHENK_BILINMIYOR = "bilinmiyor"
    AHENK_SECENEKLERI = [
        (AHENK_CALISIYOR, "Çalışıyor"),
        (AHENK_DURMUS, "Durmuş"),
        (AHENK_YOK, "Kurulu değil"),
        (AHENK_BILINMIYOR, "Bilinmiyor"),
    ]

    ad = models.CharField("Ad", max_length=100, help_text="Örn. 10-A sınıfı tahtası")
    konum = models.CharField("Konum", max_length=100, blank=True)
    makine_kimligi = models.CharField(
        "Makine kimliği", max_length=64, unique=True, help_text="/etc/machine-id"
    )
    token_ozeti = models.CharField(max_length=64, unique=True, editable=False)
    aktif = models.BooleanField(
        "Aktif", default=True, help_text="Pasif tahtanın akal-eta-yonetim uygulaması sunucuya bağlanamaz."
    )
    envanter = models.OneToOneField(
        TahtaEnvanteri,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tahta",
        verbose_name="MEB Lider kaydı",
        help_text="akal-eta-yonetim'in bildirdiği MAC adresiyle otomatik eşleşir.",
    )
    mac_adresleri = models.CharField("MAC adresleri", max_length=255, blank=True)

    hostname = models.CharField("Bilgisayar adı", max_length=100, blank=True)
    ip_adresi = models.GenericIPAddressField("IP adresi", null=True, blank=True)
    isletim_sistemi = models.CharField("İşletim sistemi", max_length=150, blank=True)
    ajan_surumu = models.CharField("akal-eta-yonetim sürümü", max_length=20, blank=True)
    acik_kalma_suresi = models.PositiveIntegerField("Açık kalma süresi (sn)", null=True, blank=True)
    ahenk_servisi = models.CharField(
        "MEB Ahenk servisi",
        max_length=12,
        choices=AHENK_SECENEKLERI,
        default=AHENK_BILINMIYOR,
    )
    meb_kayitli = models.BooleanField("MEB'e kayıtlı", null=True, blank=True)

    GUNCELLEME_SURUYOR = "suruyor"
    GUNCELLEME_BASARILI = "basarili"
    GUNCELLEME_BASARISIZ = "basarisiz"
    GUNCELLEME_YARIDA_KALDI = "yarida_kaldi"
    GUNCELLEME_SECENEKLERI = [
        (GUNCELLEME_SURUYOR, "Sürüyor"),
        (GUNCELLEME_BASARILI, "Başarılı"),
        (GUNCELLEME_BASARISIZ, "Başarısız"),
        (GUNCELLEME_YARIDA_KALDI, "Yarıda kaldı"),
    ]
    guncelleme_durumu = models.CharField(
        "Son güncelleme", max_length=12, choices=GUNCELLEME_SECENEKLERI, blank=True
    )
    guncelleme_zamani = models.DateTimeField("Son güncelleme zamanı", null=True, blank=True)

    # akal-eta-yonetim'in APT deposundan kendini güncellemesinin son sonucu.
    OTO_SURUYOR = "suruyor"
    OTO_BASARILI = "basarili"
    OTO_BASARISIZ = "basarisiz"
    OTO_GERI_DONULDU = "geri_donuldu"
    OTO_YARIDA_KALDI = "yarida_kaldi"
    OTO_GUNCELLEME_SECENEKLERI = [
        (OTO_SURUYOR, "Sürüyor"),
        (OTO_BASARILI, "Başarılı"),
        (OTO_BASARISIZ, "Başarısız"),
        (OTO_GERI_DONULDU, "Çalışmadı, geri dönüldü"),
        (OTO_YARIDA_KALDI, "Yarıda kaldı"),
    ]
    oto_guncelleme_durumu = models.CharField(
        "Son otomatik güncelleme", max_length=12, choices=OTO_GUNCELLEME_SECENEKLERI, blank=True
    )
    oto_guncelleme_hedef = models.CharField("Otomatik güncelleme hedef sürümü", max_length=20, blank=True)
    oto_guncelleme_zamani = models.DateTimeField("Son otomatik güncelleme zamanı", null=True, blank=True)
    # Tahtanın son bildirdiği açık oturumlar; her bağlantıda üzerine yazılır,
    # geçmiş tutulmaz. Öğe: {kullanici, ad, aktif, tur, baslangic (epoch sn)}.
    oturumlar = models.JSONField("Açık oturumlar", default=list, blank=True)

    # ETA envanter kaydı (ETAP'ın eta-register uygulamasının kullandığı sunucu).
    # akal-eta-yonetim günde bir kez sorgular; None: henüz sorgulanmadı / sorgulanamadı.
    eta_kayitli = models.BooleanField("ETA'ya kayıtlı", null=True, blank=True)
    eta_okul_kodu = models.CharField("ETA okul kodu", max_length=20, blank=True)
    eta_okul_adi = models.CharField("ETA okul adı", max_length=200, blank=True)
    eta_birim_adi = models.CharField("ETA birim adı", max_length=20, blank=True)
    eta_kontrol_zamani = models.DateTimeField("ETA son kontrol", null=True, blank=True)
    eta_hata = models.CharField("ETA kontrol hatası", max_length=255, blank=True)
    son_gorulme = models.DateTimeField("Son görülme", null=True, blank=True)
    kayit_tarihi = models.DateTimeField("Kayıt tarihi", auto_now_add=True)

    objects = TahtaQuerySet.as_manager()

    class Meta:
        verbose_name = "Tahta"
        verbose_name_plural = "Tahtalar"
        ordering = ["ad"]

    def __str__(self):
        return self.ad

    @property
    def aktif_oturum(self):
        """Ekranda olan (ön plandaki) oturum; tahta çevrimdışıysa None."""
        if not self.cevrimici:
            return None
        return next((o for o in self.oturumlar if o.get("aktif")), None)

    @property
    def cevrimici(self):
        return bool(self.son_gorulme and timezone.now() - self.son_gorulme <= CEVRIMICI_ESIK)


class TahtaKomutu(models.Model):
    KAPAT = "kapat"
    YENIDEN_BASLAT = "yeniden_baslat"
    GUNCELLE = "guncelle"
    ETA_KAYDET = "eta_kaydet"
    # Tahtalar sayfasındaki toplu komut düğmeleri (parametresiz komutlar).
    PANEL_KOMUTLARI = [
        (KAPAT, "Kapat"),
        (YENIDEN_BASLAT, "Yeniden başlat"),
        (GUNCELLE, "Güncelle"),
    ]
    KOMUT_SECENEKLERI = PANEL_KOMUTLARI + [
        (ETA_KAYDET, "ETA'ya kaydet / güncelle"),
    ]

    BEKLIYOR = "bekliyor"
    GONDERILDI = "gonderildi"
    TAMAMLANDI = "tamamlandi"
    BASARISIZ = "basarisiz"
    IPTAL = "iptal"
    DURUM_SECENEKLERI = [
        (BEKLIYOR, "Bekliyor"),
        (GONDERILDI, "Tahtaya gönderildi"),
        (TAMAMLANDI, "Uygulandı"),
        (BASARISIZ, "Başarısız"),
        (IPTAL, "İptal / süresi doldu"),
    ]

    tahta = models.ForeignKey(Tahta, on_delete=models.CASCADE, related_name="komutlar")
    komut = models.CharField("Komut", max_length=20, choices=KOMUT_SECENEKLERI)
    durum = models.CharField("Durum", max_length=12, choices=DURUM_SECENEKLERI, default=BEKLIYOR)
    sonuc_mesaji = models.CharField("Sonuç", max_length=255, blank=True)
    # Yalnızca parametreli komutlarda dolu; ör. eta_kaydet: {okul_kodu, birim_adi}.
    parametreler = models.JSONField("Parametreler", default=dict, blank=True)
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Oluşturan",
    )
    olusturma = models.DateTimeField("Oluşturma", auto_now_add=True)
    gonderilme = models.DateTimeField("Gönderilme", null=True, blank=True)
    tamamlanma = models.DateTimeField("Tamamlanma", null=True, blank=True)

    class Meta:
        verbose_name = "Tahta komutu"
        verbose_name_plural = "Tahta komutları"
        ordering = ["-olusturma"]

    def __str__(self):
        return f"{self.tahta} – {self.get_komut_display()}"
