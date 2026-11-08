"""
kurul — Okulda kurulması gereken kurul, komisyon ve ekipler.

- `KurulTuru` katalogdur (eğitim yılından bağımsız): adı, mevzuat dayanağı, oluşumu,
  toplanma zamanı. Mevzuat değiştikçe güncellenebilsin diye koda gömülmez; varsayılan
  katalog `kurul/fixtures/kurul_katalogu.json` dosyasından yüklenir (bkz.
  services/katalog.py).
- `Kurul` bir türün belirli bir eğitim-öğretim yılındaki örneğidir. Şube öğretmenler
  kurulu her şube, zümre öğretmenler kurulu her branş için ayrı açılır (`kapsam`).
- `KurulYapiKalemi` bir türün mevzuattaki yapısıdır (iskelet): başkan, üyeler, temsilciler;
  her kalem için üye türü, kimlerin arasından seçileceği ve asil/yedek sayısı. Kurul bu
  yapıdan oluşturulur, üyeler kalem kalem seçilir.
- `KurulUyesi` bir kurulun üyesidir: personel, öğrenci ya da yalnızca unvanı tutulan
  dış üye (veli, okul-aile birliği temsilcisi vb. — KVKK gereği ad-soyad tutulmaz).
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

GOREV_BASKAN = "baskan"
GOREV_UYE = "uye"
GOREV_CHOICES = (
    (GOREV_BASKAN, "Başkan"),
    ("baskan_yardimcisi", "Başkan Yardımcısı"),
    ("raportor", "Raportör/Yazman"),
    (GOREV_UYE, "Üye"),
    ("gozlemci", "Gözlemci"),
)


class KurulTuru(models.Model):
    KATEGORI_KURUL = "kurul"
    KATEGORI_KOMISYON = "komisyon"
    KATEGORI_EKIP = "ekip"
    KATEGORI_CHOICES = (
        (KATEGORI_KURUL, "Kurul"),
        (KATEGORI_KOMISYON, "Komisyon"),
        (KATEGORI_EKIP, "Ekip"),
    )

    KAPSAM_OKUL = "okul"
    KAPSAM_SUBE = "sube"
    KAPSAM_BRANS = "brans"
    KAPSAM_CHOICES = (
        (KAPSAM_OKUL, "Okul geneli (yılda bir kurul)"),
        (KAPSAM_SUBE, "Her sınıf/şube için ayrı"),
        (KAPSAM_BRANS, "Her branş (zümre) için ayrı"),
    )

    OTOMATIK_YOK = "yok"
    OTOMATIK_TUM_PERSONEL = "tum_personel"
    OTOMATIK_SUBE_OGRETMENLERI = "sube_ogretmenleri"
    OTOMATIK_BRANS_OGRETMENLERI = "brans_ogretmenleri"
    OTOMATIK_ZUMRE_BASKANLARI = "zumre_baskanlari"
    OTOMATIK_CHOICES = (
        (OTOMATIK_YOK, "Yok (üyeler seçilir/görevlendirilir)"),
        (OTOMATIK_TUM_PERSONEL, "Görevdeki bütün personel"),
        (OTOMATIK_SUBE_OGRETMENLERI, "Şubeye derse giren öğretmenler + rehber öğretmen"),
        (OTOMATIK_BRANS_OGRETMENLERI, "Branştaki öğretmenler"),
        (OTOMATIK_ZUMRE_BASKANLARI, "Zümre başkanları"),
    )

    kod = models.SlugField(max_length=60, unique=True, verbose_name="Kod")
    ad = models.CharField(max_length=150, verbose_name="Adı")
    kategori = models.CharField(max_length=10, choices=KATEGORI_CHOICES, verbose_name="Kategori")
    kapsam = models.CharField(
        max_length=10, choices=KAPSAM_CHOICES, default=KAPSAM_OKUL, verbose_name="Kapsam"
    )
    otomatik_uyelik = models.CharField(
        max_length=20, choices=OTOMATIK_CHOICES, default=OTOMATIK_YOK,
        verbose_name="Otomatik Üyelik",
    )
    mevzuat_dayanagi = models.CharField(max_length=255, verbose_name="Mevzuat Dayanağı")
    mevzuat_url = models.URLField(blank=True, verbose_name="Mevzuat Bağlantısı")
    olusum = models.TextField(blank=True, verbose_name="Oluşumu (mevzuata göre)")
    toplanma = models.TextField(blank=True, verbose_name="Toplanma Zamanı")
    gorev_suresi = models.CharField(max_length=60, blank=True, verbose_name="Görev Süresi")
    zorunlu = models.BooleanField(
        default=False, verbose_name="Zorunlu",
        help_text="Mevzuata göre her okulda kurulması gereken; olmayanlar ihtiyaç hâlinde kurulur.",
    )
    gizli = models.BooleanField(
        default=False, verbose_name="Gizli",
        help_text="Öğrenci kişisel verisi içeren işler (disiplin, onur kurulu). Bu uygulamada "
        "yalnızca üyelik tutulur; karar içerikleri ilgili uygulamada kalır.",
    )
    gundem_onerileri = models.TextField(
        blank=True, verbose_name="Gündem Önerileri",
        help_text="Mevzuatta bu kurulun görüşeceği konular; her satır bir öneri. Toplantı "
        "gündemi hazırlanırken listeden seçilir.",
    )
    son_dogrulama = models.DateField(
        null=True, blank=True, verbose_name="Son Doğrulama",
        help_text="Bilgilerin resmî mevzuat metniyle en son karşılaştırıldığı tarih.",
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    sira = models.PositiveSmallIntegerField(default=100, verbose_name="Sıra")

    class Meta:
        db_table = "kurul_turu"
        verbose_name = "Kurul/Komisyon Türü"
        verbose_name_plural = "Kurul/Komisyon Türleri"
        ordering = ["sira", "ad"]

    def __str__(self):
        return self.ad

    @property
    def gundem_onerisi_listesi(self):
        return [s.strip() for s in self.gundem_onerileri.splitlines() if s.strip()]


class KurulYapiKalemi(models.Model):
    """Bir kurul türünün yapısındaki tek bir görev yeri (ör. 'Öğretmenler kurulunca seçilen
    öğretmen — 2 asil, 2 yedek')."""

    UYE_PERSONEL = "personel"
    UYE_OGRENCI = "ogrenci"
    UYE_DIS = "dis"
    UYE_TURU_CHOICES = (
        (UYE_PERSONEL, "Personel"),
        (UYE_OGRENCI, "Öğrenci"),
        (UYE_DIS, "Dış üye (unvan)"),
    )

    SECIM_TUM = "tum"
    SECIM_MUDUR = "mudur"
    SECIM_YONETICI = "yonetici"
    SECIM_MUDUR_YARDIMCISI = "mudur_yardimcisi"
    SECIM_OGRETMEN = "ogretmen"
    SECIM_REHBER = "rehber"
    SECIM_CHOICES = (
        (SECIM_TUM, "Görevdeki bütün personel"),
        (SECIM_MUDUR, "Okul müdürü"),
        (SECIM_YONETICI, "Müdür / müdür yardımcıları"),
        (SECIM_MUDUR_YARDIMCISI, "Müdür yardımcıları"),
        (SECIM_OGRETMEN, "Öğretmenler"),
        (SECIM_REHBER, "Rehber öğretmenler"),
    )

    tur = models.ForeignKey(KurulTuru, on_delete=models.CASCADE, related_name="yapi", verbose_name="Tür")
    sira = models.PositiveSmallIntegerField(default=1, verbose_name="Sıra")
    unvan = models.CharField(max_length=200, verbose_name="Görev Yeri",
                             help_text="Ör. 'Öğretmenler kurulunca seçilen öğretmen'.")
    gorev = models.CharField(max_length=20, choices=GOREV_CHOICES, default=GOREV_UYE, verbose_name="Görevi")
    uye_turu = models.CharField(max_length=10, choices=UYE_TURU_CHOICES, default=UYE_PERSONEL,
                                verbose_name="Üye Türü")
    personel_secimi = models.CharField(
        max_length=20, choices=SECIM_CHOICES, default=SECIM_TUM, verbose_name="Kimler Arasından",
        help_text="Personel kalemlerinde seçim listesini daraltır.",
    )
    asil_sayisi = models.PositiveSmallIntegerField(default=1, verbose_name="Asil")
    yedek_sayisi = models.PositiveSmallIntegerField(default=0, verbose_name="Yedek")
    otomatik = models.BooleanField(
        default=False, verbose_name="Otomatik",
        help_text="Üyeler türün otomatik üyelik kuralından gelir (ders programı, branş vb.); seçilmez.",
    )

    class Meta:
        db_table = "kurul_yapi_kalemi"
        verbose_name = "Yapı Kalemi"
        verbose_name_plural = "Yapı Kalemleri"
        ordering = ["tur", "sira", "id"]

    def __str__(self):
        return f"{self.tur} — {self.unvan}"

    @property
    def sayi_metni(self):
        if self.otomatik:
            return "Otomatik"
        metin = f"{self.asil_sayisi} asil"
        if self.yedek_sayisi:
            metin += f", {self.yedek_sayisi} yedek"
        return metin


class Kurul(models.Model):
    tur = models.ForeignKey(
        KurulTuru, on_delete=models.PROTECT, related_name="kurullar", verbose_name="Tür"
    )
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili", on_delete=models.PROTECT, related_name="kurullar",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    sinif_sube = models.ForeignKey(
        "okul.SinifSube", on_delete=models.PROTECT, null=True, blank=True,
        related_name="kurullar", verbose_name="Sınıf/Şube",
    )
    brans = models.ForeignKey(
        "okul.Brans", on_delete=models.PROTECT, null=True, blank=True,
        related_name="kurullar", verbose_name="Branş",
    )
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    olusturma = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")

    class Meta:
        db_table = "kurul"
        verbose_name = "Kurul/Komisyon"
        verbose_name_plural = "Kurullar/Komisyonlar"
        ordering = ["tur__sira", "tur__ad", "sinif_sube__sinif", "sinif_sube__sube", "brans__ad"]
        constraints = [
            models.UniqueConstraint(
                fields=["tur", "egitim_yili"],
                condition=Q(sinif_sube__isnull=True, brans__isnull=True),
                name="kurul_okul_yil_tekil",
            ),
            models.UniqueConstraint(
                fields=["tur", "egitim_yili", "sinif_sube"],
                condition=Q(sinif_sube__isnull=False),
                name="kurul_sube_yil_tekil",
            ),
            models.UniqueConstraint(
                fields=["tur", "egitim_yili", "brans"],
                condition=Q(brans__isnull=False),
                name="kurul_brans_yil_tekil",
            ),
        ]

    def __str__(self):
        return self.ad

    @property
    def ad(self):
        if self.sinif_sube_id:
            return f"{self.tur.ad} — {self.sinif_sube}"
        if self.brans_id:
            return f"{self.tur.ad} — {self.brans}"
        return self.tur.ad

    def clean(self):
        super().clean()
        kapsam = self.tur.kapsam if self.tur_id else None
        if kapsam == KurulTuru.KAPSAM_SUBE and not self.sinif_sube_id:
            raise ValidationError({"sinif_sube": "Bu tür her şube için ayrı açılır; şube seçin."})
        if kapsam == KurulTuru.KAPSAM_BRANS and not self.brans_id:
            raise ValidationError({"brans": "Bu tür her branş için ayrı açılır; branş seçin."})


class KurulUyesi(models.Model):
    GOREV_BASKAN = GOREV_BASKAN
    GOREV_UYE = GOREV_UYE
    GOREV_CHOICES = GOREV_CHOICES

    kurul = models.ForeignKey(
        Kurul, on_delete=models.CASCADE, related_name="uyeler", verbose_name="Kurul"
    )
    kalem = models.ForeignKey(
        KurulYapiKalemi, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="uyeler", verbose_name="Yapıdaki Yeri",
        help_text="Boşsa yapı dışında eklenmiş ek üyedir.",
    )
    personel = models.ForeignKey(
        "okul.Personel", on_delete=models.PROTECT, null=True, blank=True,
        related_name="kurul_uyelikleri", verbose_name="Personel",
    )
    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci", on_delete=models.PROTECT, null=True, blank=True,
        related_name="kurul_uyelikleri", verbose_name="Öğrenci",
    )
    dis_uye = models.CharField(
        max_length=150, blank=True, verbose_name="Dış Üye (unvan/temsil)",
        help_text="Örn. 'Okul-Aile Birliği temsilcisi (veli)'. Ad-soyad yazılmaz.",
    )
    gorev = models.CharField(
        max_length=20, choices=GOREV_CHOICES, default=GOREV_UYE, verbose_name="Görevi"
    )
    asil = models.BooleanField(default=True, verbose_name="Asil")
    otomatik = models.BooleanField(
        default=False, verbose_name="Otomatik Eklendi",
        help_text="Ders programı/branş gibi verilerden kendiliğinden eklenen üye.",
    )
    olusturma = models.DateTimeField(auto_now_add=True, verbose_name="Eklenme")

    class Meta:
        db_table = "kurul_uyesi"
        verbose_name = "Kurul Üyesi"
        verbose_name_plural = "Kurul Üyeleri"
        ordering = ["kurul", "-asil", "gorev", "personel__adi_soyadi"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(personel__isnull=False, ogrenci__isnull=True, dis_uye="")
                    | Q(personel__isnull=True, ogrenci__isnull=False, dis_uye="")
                    | (Q(personel__isnull=True, ogrenci__isnull=True) & ~Q(dis_uye=""))
                ),
                name="kurul_uyesi_tek_kaynak",
            ),
            models.UniqueConstraint(
                fields=["kurul", "personel"], condition=Q(personel__isnull=False),
                name="kurul_uyesi_personel_tekil",
            ),
            models.UniqueConstraint(
                fields=["kurul", "ogrenci"], condition=Q(ogrenci__isnull=False),
                name="kurul_uyesi_ogrenci_tekil",
            ),
        ]

    def __str__(self):
        return f"{self.kurul} — {self.uye_adi} ({self.get_gorev_display()})"

    @property
    def uye_adi(self):
        if self.personel_id:
            return self.personel.adi_soyadi
        if self.ogrenci_id:
            o = self.ogrenci
            return f"{o.adi} {o.soyadi} ({o.sinifsube})"
        return self.dis_uye

    @property
    def gorev_adi(self):
        """Yapıdaki görev yeri varsa onun unvanı, yoksa görev adı."""
        return self.kalem.unvan if self.kalem_id else self.get_gorev_display()

    @property
    def uye_turu(self):
        if self.personel_id:
            return "Personel"
        if self.ogrenci_id:
            return "Öğrenci"
        return "Dış üye"

    def clean(self):
        super().clean()
        dolu = sum([bool(self.personel_id), bool(self.ogrenci_id), bool(self.dis_uye.strip())])
        if dolu != 1:
            raise ValidationError("Üye olarak personel, öğrenci ya da dış üye unvanından yalnızca biri girilmeli.")


# ── 2. aşama: toplantılar ────────────────────────────────────────────────────

class Toplanti(models.Model):
    """Bir kurulun toplantısı. Durum akışı: taslak → duyuruldu → yapıldı → onaylandı
    (iptal her aşamada). Onaylanan toplantı düzenlenemez (Eğitim Kurulları ve Zümreleri
    Yönergesi: kararlar müdür onayından sonra uygulanır)."""

    TUR_OLAGAN = "olagan"
    TUR_OLAGANUSTU = "olaganustu"
    TUR_CHOICES = ((TUR_OLAGAN, "Olağan"), (TUR_OLAGANUSTU, "Olağanüstü"))

    DURUM_TASLAK = "taslak"
    DURUM_DUYURULDU = "duyuruldu"
    DURUM_YAPILDI = "yapildi"
    DURUM_ONAYLANDI = "onaylandi"
    DURUM_IPTAL = "iptal"
    DURUM_CHOICES = (
        (DURUM_TASLAK, "Taslak"),
        (DURUM_DUYURULDU, "Duyuruldu"),
        (DURUM_YAPILDI, "Yapıldı (onay bekliyor)"),
        (DURUM_ONAYLANDI, "Onaylandı"),
        (DURUM_IPTAL, "İptal"),
    )

    # Yönergeye göre tarih, yer ve gündem en az bu kadar gün önce duyurulur
    DUYURU_ASGARI_GUN = 5

    kurul = models.ForeignKey(Kurul, on_delete=models.CASCADE, related_name="toplantilar", verbose_name="Kurul")
    no = models.PositiveSmallIntegerField(verbose_name="Toplantı No")
    tarih = models.DateField(verbose_name="Tarih")
    saat = models.TimeField(verbose_name="Saat")
    yer = models.CharField(max_length=150, verbose_name="Yer")
    tur = models.CharField(max_length=12, choices=TUR_CHOICES, default=TUR_OLAGAN, verbose_name="Türü")
    durum = models.CharField(max_length=12, choices=DURUM_CHOICES, default=DURUM_TASLAK, verbose_name="Durum")
    duyuru_tarihi = models.DateField(null=True, blank=True, verbose_name="Duyuru Tarihi")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    onaylayan = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Onaylayan",
    )
    onay_tarihi = models.DateField(null=True, blank=True, verbose_name="Onay Tarihi")
    olusturan = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Oluşturan",
    )
    olusturma = models.DateTimeField(auto_now_add=True, verbose_name="Oluşturulma")

    class Meta:
        db_table = "kurul_toplanti"
        verbose_name = "Toplantı"
        verbose_name_plural = "Toplantılar"
        ordering = ["tarih", "saat"]
        constraints = [
            models.UniqueConstraint(fields=["kurul", "no"], name="kurul_toplanti_no_tekil"),
        ]

    def __str__(self):
        return f"{self.kurul} — {self.no}. toplantı ({self.tarih:%d.%m.%Y})"

    @property
    def duzenlenebilir(self):
        return self.durum in (self.DURUM_TASLAK, self.DURUM_DUYURULDU, self.DURUM_YAPILDI)

    @property
    def duyuru_gun_farki(self):
        """Duyuru ile toplantı arasındaki gün sayısı (duyurulmadıysa None)."""
        if not self.duyuru_tarihi:
            return None
        return (self.tarih - self.duyuru_tarihi).days

    @property
    def duyuru_suresi_yetersiz(self):
        """Olağan toplantı 5 günden kısa sürede duyurulduysa True (yönerge uyarısı)."""
        fark = self.duyuru_gun_farki
        return self.tur == self.TUR_OLAGAN and fark is not None and fark < self.DUYURU_ASGARI_GUN


class GundemMaddesi(models.Model):
    toplanti = models.ForeignKey(Toplanti, on_delete=models.CASCADE, related_name="gundem", verbose_name="Toplantı")
    sira = models.PositiveSmallIntegerField(verbose_name="Sıra")
    baslik = models.CharField(max_length=300, verbose_name="Gündem Maddesi")
    gorusme = models.TextField(blank=True, verbose_name="Görüşme Özeti")
    onceki_kararlar = models.BooleanField(
        default=False, verbose_name="Önceki Kararlar Maddesi",
        help_text="Bir önceki toplantıda alınan kararların değerlendirildiği madde (otomatik eklenir).",
    )

    class Meta:
        db_table = "kurul_gundem_maddesi"
        verbose_name = "Gündem Maddesi"
        verbose_name_plural = "Gündem Maddeleri"
        ordering = ["toplanti", "sira"]

    def __str__(self):
        return f"{self.sira}. {self.baslik}"


class Katilim(models.Model):
    DURUM_KATILDI = "katildi"
    DURUM_MAZERETLI = "mazeretli"
    DURUM_KATILMADI = "katilmadi"
    DURUM_CHOICES = (
        (DURUM_KATILDI, "Katıldı"),
        (DURUM_MAZERETLI, "Mazeretli"),
        (DURUM_KATILMADI, "Katılmadı"),
    )

    toplanti = models.ForeignKey(Toplanti, on_delete=models.CASCADE, related_name="katilimlar", verbose_name="Toplantı")
    uye = models.ForeignKey(
        KurulUyesi, on_delete=models.SET_NULL, null=True, blank=True, related_name="katilimlar",
        verbose_name="Üye",
    )
    # Üye sonradan kuruldan çıkarılsa da tutanak bozulmasın diye toplantı anındaki bilgi
    ad = models.CharField(max_length=200, verbose_name="Adı / Unvanı")
    gorev = models.CharField(max_length=200, blank=True, verbose_name="Görevi")
    asil = models.BooleanField(default=True, verbose_name="Asil")
    durum = models.CharField(max_length=10, choices=DURUM_CHOICES, default=DURUM_KATILDI, verbose_name="Durum")
    aciklama = models.CharField(max_length=200, blank=True, verbose_name="Açıklama")

    class Meta:
        db_table = "kurul_katilim"
        verbose_name = "Katılım"
        verbose_name_plural = "Katılımlar"
        ordering = ["toplanti", "-asil", "id"]

    def __str__(self):
        return f"{self.ad} — {self.get_durum_display()}"


class Karar(models.Model):
    OYLAMA_OYBIRLIGI = "oybirligi"
    OYLAMA_OYCOKLUGU = "oycoklugu"
    OYLAMA_CHOICES = ((OYLAMA_OYBIRLIGI, "Oy birliği"), (OYLAMA_OYCOKLUGU, "Oy çokluğu"))

    TAKIP_BEKLIYOR = "bekliyor"
    TAKIP_DEVAM = "devam"
    TAKIP_TAMAM = "tamamlandi"
    TAKIP_CHOICES = (
        (TAKIP_BEKLIYOR, "Bekliyor"),
        (TAKIP_DEVAM, "Devam ediyor"),
        (TAKIP_TAMAM, "Tamamlandı"),
    )

    toplanti = models.ForeignKey(Toplanti, on_delete=models.CASCADE, related_name="kararlar", verbose_name="Toplantı")
    gundem_maddesi = models.ForeignKey(
        GundemMaddesi, on_delete=models.SET_NULL, null=True, blank=True, related_name="kararlar",
        verbose_name="Gündem Maddesi",
    )
    no = models.PositiveSmallIntegerField(verbose_name="Karar No")
    metin = models.TextField(verbose_name="Karar")
    oylama = models.CharField(max_length=10, choices=OYLAMA_CHOICES, default=OYLAMA_OYBIRLIGI, verbose_name="Oylama")
    kabul = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Kabul")
    ret = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Ret")
    cekimser = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Çekimser")
    sorumlu = models.ForeignKey(
        "okul.Personel", on_delete=models.SET_NULL, null=True, blank=True, related_name="kurul_kararlari",
        verbose_name="Sorumlu",
    )
    termin = models.DateField(null=True, blank=True, verbose_name="Termin")
    takip_durumu = models.CharField(max_length=12, choices=TAKIP_CHOICES, default=TAKIP_BEKLIYOR,
                                    verbose_name="Takip Durumu")
    takip_notu = models.CharField(max_length=300, blank=True, verbose_name="Takip Notu")

    class Meta:
        db_table = "kurul_karar"
        verbose_name = "Karar"
        verbose_name_plural = "Kararlar"
        ordering = ["toplanti", "no"]
        constraints = [
            models.UniqueConstraint(fields=["toplanti", "no"], name="kurul_karar_no_tekil"),
        ]

    def __str__(self):
        return f"Karar {self.no}: {self.metin[:60]}"

    @property
    def oylama_metni(self):
        if self.oylama == self.OYLAMA_OYCOKLUGU and self.kabul is not None:
            parca = [f"{self.kabul} kabul"]
            if self.ret:
                parca.append(f"{self.ret} ret")
            if self.cekimser:
                parca.append(f"{self.cekimser} çekimser")
            return "Oy çokluğu (" + ", ".join(parca) + ")"
        return self.get_oylama_display()

    def clean(self):
        super().clean()
        if self.oylama == self.OYLAMA_OYCOKLUGU and self.kabul is None:
            raise ValidationError({"kabul": "Oy çokluğu kararlarında kabul oyu sayısını girin."})
