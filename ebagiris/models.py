import uuid

from django.db import models
from django.utils import timezone


def _yeni_token():
    return uuid.uuid4().hex


class EbaHesap(models.Model):
    """Bir Personel'in EBA (Eğitim Bilişim Ağı) kimliğine kalıcı bağlantısı.

    Bu kayıt yalnızca kimlik doğrulanmış bir kullanıcı, kendi profilinden
    "EBA Hesabımı Bağla" akışını (bkz. views.eba_baglama_baslat/durum) bir kez
    tamamladığında oluşturulur. EBA karekod ile GİRİŞ, sisteme yeni bir hesap
    açmaz — yalnızca burada zaten bağlı bir Personel'e giriş yaptırır (bkz.
    views.eba_giris_durum). Bağlı bir EBA kimliği bulunamazsa giriş reddedilir.
    """

    personel = models.OneToOneField(
        "okul.Personel",
        on_delete=models.CASCADE,
        related_name="eba_hesap",
        verbose_name="Personel",
    )
    eba_id = models.CharField(max_length=64, unique=True, verbose_name="EBA Kimliği")
    eba_adi_soyadi = models.CharField(
        max_length=150, blank=True, verbose_name="EBA'daki Ad Soyad"
    )
    baglanma_zamani = models.DateTimeField(default=timezone.now, verbose_name="Bağlanma Zamanı")

    class Meta:
        db_table = "ebagiris_hesap"
        verbose_name = "EBA Hesabı"
        verbose_name_plural = "EBA Hesapları"

    def __str__(self):
        return f"{self.personel} — EBA:{self.eba_id}"


class EbaOturum(models.Model):
    """Tek bir EBA karekod akışının (giriş ya da hesap bağlama) durumu.

    `eba_ws_worker` yönetim komutu arka planda EBA'yla (ya da geliştirmede
    `eba_mock_sunucu` ile) websocket üzerinden konuşup bu satırı günceller;
    giriş/profil sayfasındaki JS, `token` ile kısa aralıklarla durum sorgusu
    yaparak (bkz. views.eba_giris_durum / eba_baglama_durum) QR'ı ve sonucu
    gösterir. HTTP isteklerinin (senkron Django view'ları) EBA'nın uzun ömürlü
    websocket bağlantısını doğrudan yönetmemesi için bu satır aradaki köprüdür
    — aynı ebaqr-greeter projesindeki loopback-HTTP köprüsünün burada
    veritabanı satırına karşılık gelen hâli.
    """

    AMAC_GIRIS = "giris"
    AMAC_BAGLAMA = "baglama"
    AMAC_CHOICES = [
        (AMAC_GIRIS, "Giriş"),
        (AMAC_BAGLAMA, "Hesap Bağlama"),
    ]

    DURUM_BEKLIYOR = "bekliyor"  # worker henüz EBA'ya bağlanmadı
    DURUM_QR_HAZIR = "qr_hazir"  # QR üretildi, taranması bekleniyor
    DURUM_DOGRULANDI = "dogrulandi"  # EBA doğruladı, worker eba_id'yi yazdı
    DURUM_TAMAMLANDI = "tamamlandi"  # view login/bağlama işlemini bitirdi
    DURUM_SURESI_DOLDU = "suresi_doldu"
    DURUM_HATA = "hata"
    DURUM_CHOICES = [
        (DURUM_BEKLIYOR, "Bekliyor"),
        (DURUM_QR_HAZIR, "QR Hazır"),
        (DURUM_DOGRULANDI, "Doğrulandı"),
        (DURUM_TAMAMLANDI, "Tamamlandı"),
        (DURUM_SURESI_DOLDU, "Süresi Doldu"),
        (DURUM_HATA, "Hata"),
    ]

    token = models.CharField(max_length=32, unique=True, default=_yeni_token, editable=False)
    amac = models.CharField(max_length=10, choices=AMAC_CHOICES, verbose_name="Amaç")
    durum = models.CharField(
        max_length=15, choices=DURUM_CHOICES, default=DURUM_BEKLIYOR, verbose_name="Durum"
    )

    # AMAC_BAGLAMA akışında: hangi personel bağlıyor (kimlik doğrulanmış kullanıcı,
    # baştan bilinir). AMAC_GIRIS akışında boştur — eşleşen personel EBA'nın
    # doğruladığı eba_id'ye göre sonradan bulunur (bkz. eslesen_personel).
    baglanacak_personel = models.ForeignKey(
        "okul.Personel",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Bağlanacak Personel",
    )

    qr_uuid = models.CharField(max_length=64, blank=True, verbose_name="QR İçeriği")
    qr_expire_at = models.DateTimeField(null=True, blank=True, verbose_name="QR Son Kullanma")

    eba_id = models.CharField(max_length=64, blank=True, verbose_name="Doğrulanan EBA Kimliği")
    eba_adi_soyadi = models.CharField(max_length=150, blank=True, verbose_name="EBA'daki Ad Soyad")

    # AMAC_GIRIS akışında: eba_id, EbaHesap üzerinden eşleşince bulunan personel.
    eslesen_personel = models.ForeignKey(
        "okul.Personel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Eşleşen Personel",
    )

    mesaj = models.CharField(max_length=300, blank=True, verbose_name="Mesaj")
    olusturma_zamani = models.DateTimeField(auto_now_add=True)
    guncelleme_zamani = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ebagiris_oturum"
        verbose_name = "EBA Oturumu"
        verbose_name_plural = "EBA Oturumları"
        ordering = ["-olusturma_zamani"]

    def __str__(self):
        return f"{self.get_amac_display()} — {self.token[:8]} ({self.get_durum_display()})"

    def suresi_doldu_mu(self):
        return bool(self.qr_expire_at and timezone.now() > self.qr_expire_at)
