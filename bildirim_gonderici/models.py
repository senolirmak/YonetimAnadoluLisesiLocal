from django.contrib.auth.models import User
from django.db import models

from okul.models import SinifSube


class SinifTahta(models.Model):
    """Sınıftaki etkileşimli tahtanın ağ bilgileri."""

    sinif_sube = models.OneToOneField(
        SinifSube,
        on_delete=models.CASCADE,
        related_name="tahta",
        verbose_name="Sınıf/Şube",
    )
    ip_adresi = models.GenericIPAddressField(
        protocol="IPv4",
        verbose_name="IP Adresi",
    )
    port = models.PositiveIntegerField(
        default=8765,
        verbose_name="Port",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    aciklama = models.CharField(max_length=200, blank=True, verbose_name="Açıklama")

    class Meta:
        verbose_name = "Sınıf Tahtası"
        verbose_name_plural = "Sınıf Tahtaları"
        ordering = ["sinif_sube__sinif", "sinif_sube__sube"]

    def __str__(self):
        return f"{self.sinif_sube} — {self.ip_adresi}:{self.port}"

    @property
    def url(self):
        return f"http://{self.ip_adresi}:{self.port}/bildirim"


class BildirimLog(models.Model):
    """Gönderilen her bildirimin kaydı."""

    TUR_CAGRI = "cagri"
    TUR_DUYURU = "duyuru"
    TUR_TEST = "test"
    TUR_CHOICES = [
        (TUR_CAGRI, "Öğrenci Çağrısı"),
        (TUR_DUYURU, "Duyuru"),
        (TUR_TEST, "Test"),
    ]

    DURUM_BASARILI = "basarili"
    DURUM_BASARISIZ = "basarisiz"
    DURUM_CHOICES = [
        (DURUM_BASARILI, "Başarılı"),
        (DURUM_BASARISIZ, "Başarısız"),
    ]

    tahta = models.ForeignKey(
        SinifTahta,
        on_delete=models.SET_NULL,
        null=True,
        related_name="bildirimler",
        verbose_name="Hedef Tahta",
    )
    tur = models.CharField(max_length=10, choices=TUR_CHOICES, verbose_name="Tür")
    baslik = models.CharField(max_length=200, verbose_name="Başlık")
    mesaj = models.TextField(verbose_name="Mesaj")
    gonderen = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Gönderen",
    )
    gonderim_zamani = models.DateTimeField(auto_now_add=True, verbose_name="Gönderim Zamanı")
    durum = models.CharField(max_length=12, choices=DURUM_CHOICES, verbose_name="Durum")
    hata_mesaji = models.TextField(blank=True, verbose_name="Hata Mesajı")

    class Meta:
        verbose_name = "Bildirim Kaydı"
        verbose_name_plural = "Bildirim Kayıtları"
        ordering = ["-gonderim_zamani"]

    def __str__(self):
        tahta_str = str(self.tahta) if self.tahta else "—"
        return f"{self.get_tur_display()} → {tahta_str} | {self.gonderim_zamani:%d.%m.%Y %H:%M}"
