"""
okul — Okul Yönetim Sistemi merkezi modeller.

Bu app, sistem genelinde paylaşılan temel modellere ev sahipliği yapar.
Diğer app'ler bu modellere FK ile bağlanır; kendi içlerinde kopya tanımlamaz.
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Takvim modelleri
# ---------------------------------------------------------------------------

class EgitimOgretimYili(models.Model):
    egitim_yili = models.CharField(
        max_length=9,
        unique=True,
        verbose_name="Eğitim-Öğretim Yılı",
        help_text="Örnek: 2025-2026",
    )
    egitim_baslangic = models.DateField(verbose_name="Yıl Başlangıç Tarihi")
    egitim_bitis = models.DateField(verbose_name="Yıl Bitiş Tarihi")

    class Meta:
        db_table = "egitim_ogretim_yili"
        verbose_name = "Eğitim-Öğretim Yılı"
        verbose_name_plural = "Eğitim-Öğretim Yılları"
        ordering = ["-egitim_yili"]

    def __str__(self):
        return self.egitim_yili


class OkulDonem(models.Model):
    DONEM_CHOICES = (
        (1, "1. Dönem"),
        (2, "2. Dönem"),
    )

    egitim_yili = models.ForeignKey(
        "EgitimOgretimYili",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="donemleri",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    donem = models.PositiveSmallIntegerField(
        choices=DONEM_CHOICES,
        verbose_name="Dönem",
    )
    baslangic = models.DateField(verbose_name="Başlangıç Tarihi")
    bitis = models.DateField(verbose_name="Bitiş Tarihi")

    class Meta:
        db_table = "okul_donem"
        unique_together = ("egitim_yili", "donem")
        verbose_name = "Okul Dönemi"
        verbose_name_plural = "Okul Dönemleri"
        ordering = ["baslangic"]

    def __str__(self):
        donem_adi = dict(self.DONEM_CHOICES).get(self.donem, str(self.donem))
        return f"{donem_adi}"


class OkulBilgi(models.Model):
    okul_kodu = models.CharField(max_length=20, blank=True, verbose_name="Okul Kodu")
    okul_adi = models.CharField(max_length=200, blank=True, verbose_name="Okul Adı")
    okul_muduru = models.CharField(max_length=100, blank=True, verbose_name="Okul Müdürü")
    okul_donem = models.ForeignKey(
        "OkulDonem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Aktif Dönem",
    )
    okul_egtyil = models.ForeignKey(
        "EgitimOgretimYili",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Aktif Eğitim-Öğretim Yılı",
    )

    class Meta:
        db_table = "okul_bilgi"
        verbose_name = "Okul Bilgisi"
        verbose_name_plural = "Okul Bilgileri"

    def __str__(self):
        return self.okul_adi or "Okul Bilgisi"

    @classmethod
    def get(cls):
        """Singleton erişim."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ---------------------------------------------------------------------------
# Sınıf/Şube modeli
# ---------------------------------------------------------------------------

class SinifSube(models.Model):
    sinif = models.IntegerField()
    sube = models.CharField(max_length=2)

    class Meta:
        db_table = "nobet_sinifsube"
        unique_together = ("sinif", "sube")
        verbose_name = "Sınıf Şube"
        verbose_name_plural = "Sınıf ve Şubeler"

    def __str__(self):
        return f"{self.sinif}/{self.sube}"

    @property
    def sinif_sube(self):
        return f"{self.sinif}/{self.sube}"

    @property
    def sinifsube(self):
        return f"{self.sinif}/{self.sube}"

    @property
    def salon(self):
        return f"Salon {self.sinif}/{self.sube}"

    def acik_mi(self, egitim_yili=None):
        """`egitim_yili` (verilmezse aktif eğitim-öğretim yılı) için bu sınıf/şubenin
        açık olup olmadığını döner. Açık/kapalı durumu artık SinifSube üzerinde tek bir
        bayrak değil, yıla göre değişebilen `SinifSubeYil` kayıtlarında tutulur — aynı
        şube bir yıl açık, ertesi yıl kapalı, sonraki yıl yeniden açık olabilir (bkz.
        commit geçmişi). O yıl için hiç kayıt yoksa varsayılan olarak açık sayılır
        (yeni tanımlanan/henüz değerlendirilmemiş bir şube varsayılan açıktır).
        """
        yil = egitim_yili
        if yil is None:
            from okul.utils import get_aktif_egitim_yili
            yil = get_aktif_egitim_yili()
        if yil is None:
            return True
        durum = self.yil_durumlari.filter(egitim_yili=yil).values_list("acik", flat=True).first()
        return True if durum is None else durum


class SinifSubeYil(models.Model):
    """Bir `SinifSube`nin belirli bir eğitim-öğretim yılındaki açık/kapalı durumu.

    Her (sınıf/şube, yıl) çifti için ayrı bir kayıt tutulur — böylece örn. 9/G bir
    yıl açık, ertesi yıl kapalı, sonraki yıl yeniden açık olabilir; tek bir global
    bayrak bu geçmişi temsil edemez (bkz. commit geçmişi).
    """

    sinif_sube = models.ForeignKey(
        SinifSube,
        on_delete=models.CASCADE,
        related_name="yil_durumlari",
        verbose_name="Sınıf Şube",
    )
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.CASCADE,
        related_name="sinif_sube_durumlari",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    acik = models.BooleanField(
        default=True,
        verbose_name="Açık",
        help_text="Kapalı şubelere bu yıl için yeni öğrenci atanamaz.",
    )

    class Meta:
        db_table = "nobet_sinifsubeyil"
        unique_together = ("sinif_sube", "egitim_yili")
        ordering = ["-egitim_yili__egitim_baslangic"]
        verbose_name = "Sınıf Şube — Yıl Durumu"
        verbose_name_plural = "Sınıf Şube Yıl Durumları"

    def __str__(self):
        durum = "Açık" if self.acik else "Kapalı"
        return f"{self.sinif_sube} — {self.egitim_yili} ({durum})"


# ---------------------------------------------------------------------------
# Ders modelleri
# ---------------------------------------------------------------------------

class DersHavuzu(models.Model):
    """e-Okul haftalık ders programından elde edilen tekil ders adı havuzu."""

    CIFT_OTURUM_CHOICES = [
        (0, "Yazılı"),
        (1, "Yazılı + Uygulama"),
    ]

    ders_adi = models.CharField(max_length=200, unique=True)
    cift_oturum = models.PositiveSmallIntegerField(
        choices=CIFT_OTURUM_CHOICES,
        default=0,
        verbose_name="Sınav Türü",
    )
    sinav_yapilmayacak = models.BooleanField(
        default=False,
        verbose_name="Sınav Yapılmayacak",
        help_text="Bu dersten ortak sınav yapılmaz (Beden Eğitimi, Müzik vb.)",
    )

    class Meta:
        db_table = "sinav_dershavuzu"
        ordering = ["ders_adi"]
        verbose_name = "Ders"
        verbose_name_plural = "Ders Havuzu"

    def __str__(self):
        return self.ders_adi


class DersSaatleri(models.Model):
    derssaati_no = models.PositiveIntegerField(verbose_name="Ders No", unique=True)
    derssaati_baslangic = models.TimeField(verbose_name="Ders Başlangıç")
    derssaati_bitis = models.TimeField(verbose_name="Ders Bitiş")

    class Meta:
        db_table = "sinav_derssaatleri"
        ordering = ["derssaati_no"]
        verbose_name = "Ders Saati"
        verbose_name_plural = "Ders Saatleri"

    @property
    def ders_adi(self):
        return f"{self.derssaati_no}. Ders"

    def __str__(self):
        return f"{self.ders_adi} ({self.derssaati_baslangic:%H:%M} – {self.derssaati_bitis:%H:%M})"


# ---------------------------------------------------------------------------
# Branş modeli
# ---------------------------------------------------------------------------

class Brans(models.Model):
    ad = models.CharField(max_length=50, unique=True, verbose_name="Branş Adı")

    class Meta:
        db_table = "okul_brans"
        ordering = ["ad"]
        verbose_name = "Branş"
        verbose_name_plural = "Branşlar"

    def __str__(self):
        return self.ad


# ---------------------------------------------------------------------------
# Personel modeli
# ---------------------------------------------------------------------------

class Personel(models.Model):
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
    brans = models.ForeignKey(
        "Brans",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="personeller",
        verbose_name="Branş",
    )
    mezunokul = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="Mezun Olduğu Yükseköğretim Programı/Fakülte",
    )
    CINSIYET_CHOICES = (
        (True, "Erkek"),
        (False, "Kadın"),
    )
    cinsiyet = models.BooleanField(default=True, choices=CINSIYET_CHOICES)
    nobeti_var = models.BooleanField(default=True)
    GOREVI_CHOICES = (
        ("Öğretmen", "Öğretmen"),
        ("Müdür", "Müdür"),
        ("Okul Müdürü", "Okul Müdürü"),
        ("Müdür Yardımcısı", "Müdür Yardımcısı"),
        ("Ücretli Öğretmen", "Ücretli Öğretmen"),
        ("Görevlendirme", "Görevlendirme"),
        ("Rehberlik", "Rehberlik"),
        ("YEĞİTEK Okul Sorumlusu", "YEĞİTEK Okul Sorumlusu"),
    )
    gorev_tipi = models.CharField(
        max_length=50, choices=GOREVI_CHOICES, blank=True, null=True, verbose_name="Görevi",
    )
    DURUM_CHOICES = (
        ("Görevde", "Görevde"),
        ("Dış Görevde", "Dış Görevde"),
        ("Aylıksız İzinli", "Aylıksız İzinli"),
        ("Analık İzinli", "Analık İzinli"),
        ("Görevlendirme Sona Erdi", "Görevlendirme Sona Erdi"),
        ("Emekli", "Emekli"),
        ("Ayrıldı-Tayin", "Ayrıldı-Tayin"),
        ("Açığa Alındı", "Açığa Alındı"),
    )
    durum = models.CharField(
        max_length=30, choices=DURUM_CHOICES, default="Görevde", verbose_name="Durum",
    )
    sabit_nobet = models.BooleanField(default=False)

    class Meta:
        db_table = "nobet_personel"
        verbose_name = "Personel"
        verbose_name_plural = "Personel Listesi"

    def __str__(self):
        return self.adi_soyadi


# ---------------------------------------------------------------------------
# Veri aktarım geçmişi
# ---------------------------------------------------------------------------

class VeriAktarimGecmisi(models.Model):
    DOSYA_TURU_CHOICES = [
        ("ders_programi", "Haftalık Ders Programı"),
        ("nobet_listesi", "Nöbet Listesi"),
        ("ogrenci_listesi", "Öğrenci Listesi"),
        ("personel_listesi", "Personel Listesi"),
    ]
    DURUM_CHOICES = [
        ("basarili", "Başarılı"),
        ("kismi", "Kısmi (uyarılarla tamamlandı)"),
        ("hatali", "Hatalı"),
    ]

    dosya_turu = models.CharField(
        max_length=20,
        choices=DOSYA_TURU_CHOICES,
        verbose_name="Dosya Türü",
    )
    dosya_adi = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Dosya Adı",
    )
    uygulama_tarihi = models.DateField(
        null=True,
        blank=True,
        verbose_name="Uygulama Tarihi",
        help_text="Verinin geçerli olduğu tarih (haftalık program / nöbet listesi için)",
    )
    dosya_tarihi = models.DateField(
        null=True,
        blank=True,
        verbose_name="Dosya Tarihi",
        help_text="e-Okul'dan alınan dosyanın ait olduğu tarih (öğrenci listesi için)",
    )
    yukleme_tarihi = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Yükleme Tarihi",
    )
    kullanici = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="veri_aktarimlari",
        verbose_name="Yükleyen",
    )
    kayit_sayisi = models.PositiveIntegerField(
        default=0,
        verbose_name="İşlenen Kayıt",
    )
    hata_sayisi = models.PositiveIntegerField(
        default=0,
        verbose_name="Hatalı Kayıt",
    )
    otomatik_eklenen = models.PositiveIntegerField(
        default=0,
        verbose_name="Otomatik Eklenen",
        help_text="Sistemde bulunmayıp otomatik oluşturulan kayıt sayısı",
    )
    durum = models.CharField(
        max_length=10,
        choices=DURUM_CHOICES,
        default="basarili",
        verbose_name="Durum",
    )
    notlar = models.TextField(
        blank=True,
        verbose_name="Notlar",
        help_text="Uyarılar, otomatik oluşturulan isimler vb.",
    )

    class Meta:
        db_table = "okul_veri_aktarim_gecmisi"
        verbose_name = "Veri Aktarım Kaydı"
        verbose_name_plural = "Veri Aktarım Geçmişi"
        ordering = ["-yukleme_tarihi"]

    def __str__(self):
        turu = dict(self.DOSYA_TURU_CHOICES).get(self.dosya_turu, self.dosya_turu)
        tarih = self.yukleme_tarihi.strftime("%d.%m.%Y %H:%M") if self.yukleme_tarihi else ""
        return f"{turu} — {tarih}"


# ---------------------------------------------------------------------------
# Yönetici profil modeli
# ---------------------------------------------------------------------------

class OkulYonetici(models.Model):
    """
    Okul yöneticisi (müdür veya müdür yardımcısı) profil kaydı.

    Django'nun Group tabanlı yetki sistemi ile birlikte çalışır:
    yetki kontrolü okul.auth.is_mudur_yardimcisi() üzerinden yapılır.
    Bu model ek profil bilgilerini (unvan, personel bağlantısı, aktiflik) saklar.
    """

    UNVAN_CHOICES = [
        ("okul_muduru", "Okul Müdürü"),
        ("mudur_yardimcisi", "Müdür Yardımcısı"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="okul_yonetici",
        verbose_name="Kullanıcı",
    )
    personel = models.OneToOneField(
        "okul.Personel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="okul_yonetici",
        verbose_name="Personel",
    )
    unvan = models.CharField(
        max_length=20,
        choices=UNVAN_CHOICES,
        default="mudur_yardimcisi",
        verbose_name="Unvan",
    )
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
        help_text="Pasif yapılırsa yetki kontrolü reddeder.",
    )

    class Meta:
        verbose_name = "Okul Yöneticisi"
        verbose_name_plural = "Okul Yöneticileri"

    def __str__(self):
        unvan_label = dict(self.UNVAN_CHOICES).get(self.unvan, self.unvan)
        isim = self.user.get_full_name() or self.user.username
        return f"{isim} ({unvan_label})"

    @property
    def adi_soyadi(self) -> str:
        if self.personel_id:
            return self.personel.adi_soyadi
        return self.user.get_full_name() or self.user.username


# ---------------------------------------------------------------------------
# Aktif veri konfigürasyonu
# ---------------------------------------------------------------------------

class AktifVeriKonfigurasyonu(models.Model):
    """
    Her veri türü için hangi uygulama_tarihi'nin aktif (geçerli) olduğunu tutar.
    Import servisleri başarılı yüklemede bu tabloyu günceller.
    Tarihsiz DersProgrami sorguları bu tablodan aktif tarihi okur.
    """

    VERI_TURU_CHOICES = [
        ("ders_programi", "Haftalık Ders Programı"),
        ("personel_listesi", "Personel Listesi"),
        ("nobet_listesi", "Nöbet Listesi"),
        ("sinif_sube", "Sınıf/Şube Listesi"),
    ]

    veri_turu = models.CharField(
        max_length=20,
        choices=VERI_TURU_CHOICES,
        unique=True,
        verbose_name="Veri Türü",
    )
    uygulama_tarihi = models.DateField(verbose_name="Aktif Uygulama Tarihi")
    guncelleme_tarihi = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")

    class Meta:
        db_table = "okul_aktif_veri_konfigurasyonu"
        verbose_name = "Aktif Veri Konfigürasyonu"
        verbose_name_plural = "Aktif Veri Konfigürasyonları"

    def __str__(self):
        turu = dict(self.VERI_TURU_CHOICES).get(self.veri_turu, self.veri_turu)
        return f"{turu} → {self.uygulama_tarihi}"


# ---------------------------------------------------------------------------
# TTKB Öğretmenlik Alanları, Atama ve Ders Okutma Esasları (resmi çizelge)
# ---------------------------------------------------------------------------

class OgretmenlikAlanCizelgesi(models.Model):
    """
    MEB Talim ve Terbiye Kurulu Başkanlığı'nın "Öğretmenlik Alanları, Atama ve
    Ders Okutma Esasları" çizelgesinden içe aktarılan resmi referans tablosu.
    Her satır bir (branş, mezuniyet programı) çiftini ve o çiftin okutabileceği
    dersleri temsil eder — aynı branşın farklı mezuniyet programları farklı
    ders yetkisine sahip olabildiğinden (örn. Din Kültürü ve Ahlâk Bilgisi'nde
    İlahiyat mezunları ilköğretim mezunlarından daha geniş bir ders listesi
    okutabilir), granülerlik branş değil bu çift bazındadır.
    Elle düzenlenmez — `ttkb_cizelge_yukle` komutuyla TTKB PDF'inden içe aktarılır.
    """

    sira_no = models.PositiveSmallIntegerField(
        verbose_name="Sıra No",
        help_text="Çizelgedeki SIRA NO sütunu (aynı sıra no birden fazla branşı kapsayabilir).",
    )
    brans = models.CharField(max_length=200, verbose_name="Atamaya Esas Olan Alan (Branş)")
    mezunokul = models.CharField(
        max_length=300,
        blank=True,
        verbose_name="Mezun Olduğu Yükseköğretim Programı/Fakülte",
    )
    dersler = models.TextField(verbose_name="Okutacağı Dersler")
    kaynak_sayfa = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Kaynak PDF Sayfası",
    )

    class Meta:
        db_table = "okul_ttkb_ogretmenlik_alan_cizelgesi"
        unique_together = [("sira_no", "brans", "mezunokul")]
        ordering = ["sira_no", "brans", "mezunokul"]
        verbose_name = "Öğretmenlik Alanı Çizelgesi (TTKB)"
        verbose_name_plural = "Öğretmenlik Alanları Çizelgesi (TTKB)"

    def __str__(self):
        return f"{self.brans} — {self.mezunokul}"
