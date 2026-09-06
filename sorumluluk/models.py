from django.db import models


SALON_KAPASITESI = 30


class SorumlulukSalon(models.Model):
    """Sorumluluk sınavlarında görevlendirme ve oturma planında kullanılacak salon
    tanımı — okul/yonetim/personel sayfasındaki gibi ayrı bir CRUD'dan yönetilir.

    `sira`, ekranlarda/PDF'lerde görünen sabit "Salon 1", "Salon 2", ... etiketini ve
    iç kodu (`kod`, bkz. aşağı) belirler; `ad` ise idarecinin o pozisyona verdiği
    okunabilir isimdir — jenerik bir salon adı ("Mazeret 1") ya da gerçek bir sınıf
    adı ("10/A Sınıfı") olabilir, istenildiği zaman değiştirilebilir.

    Tüm sorumluluk sınavları için ortaktır (SorumluGorevMuafPersonel ile aynı ilke —
    sınava özgü değildir). Bir salon geçici olarak kullanım dışı bırakılacaksa
    silinmez, `aktif=False` yapılır: yeni takvim/oturma planı üretiminde bu salon
    kullanılmaz, ama `kod`'u geçmiş SorumluGozetmen/SorumluOturmaPlani kayıtlarında
    serbest metin olarak durmaya devam ettiğinden geçmiş sınavların verisi bozulmaz.

    Kapasite kasıtlı olarak salon başına değil, tüm salonlar için ortak/sabit
    `SALON_KAPASITESI` üzerinden tutulur (basit tutmak için bilinçli tercih).
    """
    sira = models.PositiveSmallIntegerField(unique=True, verbose_name="Sıra (Salon No)")
    ad = models.CharField(max_length=50, verbose_name="Salon Adı")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    class Meta:
        ordering = ["sira"]
        verbose_name = "Salon"
        verbose_name_plural = "Salonlar"

    def __str__(self):
        return f"Salon {self.sira} ({self.ad})"

    @property
    def kod(self):
        """SorumluGozetmen/SorumluOturmaPlani.salon alanında saklanan iç değer."""
        return f"Sorumluluk{self.sira}"


def salon_choices():
    """SorumluGozetmen/SorumluOturmaPlani.salon alanında saklanan (kod, ad) çiftleri.

    NOT: bu alan kasıtlı olarak `choices=` almaz — Django, bir CharField'ın
    `choices` değeri callable olsa bile bunu `manage.py check`/migration
    doğrulaması sırasında hemen değerlendirir; bu da SorumlulukSalon tablosu
    henüz yokken (ör. ilk migrate öncesi) DB hatasına yol açar. Bunun yerine
    salon adı görüntülenmesi gereken her yerde (rapor/pdf servisleri) bu
    fonksiyon doğrudan çağrılır — bkz. `_salon_label` yardımcıları.

    Aktif olmayan salonlar da dahil edilir: aksi halde eskiden kullanılmış ama
    artık pasif bir salona ait geçmiş kayıtlarda adı bulunamaz. Yeni atama
    üretimi (takvim_service.py) ayrıca `aktif=True` filtresi uygular.
    """
    return [(s.kod, s.ad) for s in SorumlulukSalon.objects.order_by("sira")]


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
    arsivlendi       = models.BooleanField(default=False, verbose_name="Arşivlendi")
    arsivlenme_tarihi = models.DateTimeField(null=True, blank=True, verbose_name="Arşivlenme Tarihi")

    class Meta:
        ordering = ["-olusturma_tarihi"]
        verbose_name = "Sorumluluk Sınavı"
        verbose_name_plural = "Sorumluluk Sınavları"

    def __str__(self):
        egitim = str(self.egitim_yili) if self.egitim_yili_id else ""
        donem  = self.get_donem_turu_display()
        return f"{self.sinav_adi} ({egitim} {donem})".strip()

    def gorevlendirme_yapilmis_mi(self) -> bool:
        """Sınava ait en az bir komisyon üyesi veya gözetmen görevlendirmesi yapılmış mı?"""
        from django.db.models import Q
        return (
            self.komisyon_uyeler.filter(Q(uye1__isnull=False) | Q(uye2__isnull=False)).exists()
            or self.gozetmenler.filter(gozetmen__isnull=False).exists()
        )

    def arsivlenebilir_mi(self) -> bool:
        """'Arşivle' işlemi için uygun mu: onaylanmış ve görevlendirmesi yapılmış,
        henüz arşivlenmemiş olmalı."""
        return self.onaylandi and not self.arsivlendi and self.gorevlendirme_yapilmis_mi()

    def silinebilir_mi(self) -> bool:
        """Arşivlenmiş sınavlar silinemez; arşivlenmemiş sınavlar (taslak, onaylı
        ama henüz arşivlenmemiş vb.) silinebilir."""
        return not self.arsivlendi


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
    brans        = models.ForeignKey(
        "okul.Brans", on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="sorumluluk_ders_havuzu", verbose_name="Branş",
        help_text="Haftalık Ders Programı'ndaki öğretmen atamalarından otomatik belirlenir.",
    )

    class Meta:
        ordering = ["onceki_sinif", "ders_adi"]
        unique_together = [("sinav", "ders_adi", "onceki_sinif")]
        verbose_name = "Sorumlu Ders Havuzu"
        verbose_name_plural = "Sorumlu Ders Havuzu"

    def __str__(self):
        return f"{self.ders_adi} ({self.onceki_sinif}. Sınıf)"


class SorumluDersKatalogu(models.Model):
    """Sınava ait, sınıf seviyesinden bağımsız bilgilendirme amaçlı ders adı listesi.

    e-Okul verisi çekildiğinde öğrencilerin sorumlu derslerinden faydalanılarak
    otomatik doldurulur (sadece ekleme yapılır, mevcut kayıt silinmez).
    SorumluDersHavuzu / SorumluDers ile hiçbir FK ilişkisi yoktur; bu nedenle
    buradan bir dersin silinmesi sınav planlamasını (takvim algoritmasını) etkilemez.
    """
    sinav      = models.ForeignKey(
        SorumluSinav, on_delete=models.CASCADE,
        related_name="ders_katalogu", verbose_name="Sınav",
    )
    okul_dersi = models.ForeignKey(
        "okul.DersHavuzu", on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="sorumluluk_ders_katalogu", verbose_name="Okul Ders Havuzu Kaydı",
        help_text=(
            "Ders adı, Okul Ders Havuzu'ndaki bir kayıtla eşleşiyorsa otomatik bağlanır. "
            "Nakil öğrenci nedeniyle Okul Ders Havuzu'nda karşılığı olmayan dersler boş "
            "kalabilir (bkz. Okul Ders Havuzu Önerileri)."
        ),
    )
    ders_adi   = models.CharField(max_length=200, verbose_name="Ders Adı")
    branslar   = models.ManyToManyField(
        "okul.Brans", blank=True,
        related_name="sorumluluk_ders_katalogu", verbose_name="Branşlar",
        help_text=(
            "secmelidersler'deki (Ortak/Seçmeli Ders Havuzu) aynı adlı kayıtların "
            "branşlarından tespit edilen yeni eşleşmeler, doğrudan eklenmeden önce onayınıza sunulur "
            "(bkz. Branş Önerileri). Buradan elle de ekleyip çıkarabilirsiniz. Bazı dersler "
            "(örn. GÖRSEL SANATLAR/MÜZİK) birden fazla branştan öğretmen tarafından okutulabilir."
        ),
    )
    ortak_ders = models.ForeignKey(
        "secmelidersler.OrtakDersHavuzu", on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="+", verbose_name="Eşleşen Ortak Ders (Havuz)",
        help_text=(
            "Ders adı otomatik eşleşmediğinde elle bağlanabilir; branşlar buradan "
            "senkronize edilir. Seçmeli Ders ile birlikte seçilemez."
        ),
    )
    secmeli_ders = models.ForeignKey(
        "secmelidersler.SecmeliDersHavuzu", on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="+", verbose_name="Eşleşen Seçmeli Ders (Havuz)",
        help_text=(
            "Ders adı otomatik eşleşmediğinde elle bağlanabilir; branşlar buradan "
            "senkronize edilir. Ortak Ders ile birlikte seçilemez."
        ),
    )

    class Meta:
        ordering = ["ders_adi"]
        unique_together = [("sinav", "ders_adi")]
        constraints = [
            models.CheckConstraint(
                condition=~(
                    models.Q(ortak_ders__isnull=False) & models.Q(secmeli_ders__isnull=False)
                ),
                name="sorumluderskatalogu_tek_secmeli_ders_turu",
            ),
        ]
        verbose_name = "Ders Kataloğu"
        verbose_name_plural = "Ders Kataloğu"

    def __str__(self):
        return self.ders_adi


class SorumluDersKatalogBransOneri(models.Model):
    """Ders Kataloğu'ndaki bir derse, Haftalık Ders Programı'ndan tespit edilen ancak
    henüz kullanıcı tarafından onaylanmamış branş önerisi.

    Onaylanınca ilgili branş SorumluDersKatalogu.branslar'a eklenir ve bu kayıt silinir.
    Reddedilirse sadece bu kayıt silinir (branş eklenmez); sonraki bir e-Okul
    aktarımında ders programı hâlâ aynı eşleşmeyi gösteriyorsa öneri yeniden oluşabilir.
    """
    katalog = models.ForeignKey(
        SorumluDersKatalogu, on_delete=models.CASCADE,
        related_name="brans_onerileri", verbose_name="Ders",
    )
    brans = models.ForeignKey(
        "okul.Brans", on_delete=models.CASCADE,
        related_name="+", verbose_name="Önerilen Branş",
    )
    olusturma_tarihi = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("katalog", "brans")]
        ordering = ["katalog__ders_adi"]
        verbose_name = "Branş Önerisi"
        verbose_name_plural = "Branş Önerileri"

    def __str__(self):
        return f"{self.katalog.ders_adi} → {self.brans.ad} (onay bekliyor)"


class SorumluDersKatalogOkulDersOnerisi(models.Model):
    """Ders Kataloğu'ndaki, Okul Ders Havuzu'nda karşılığı bulunamayan (örn. nakil
    öğrenci nedeniyle) bir dersin Okul Ders Havuzu'na eklenmesi için onay bekleyen öneri.

    Onaylanınca okul.DersHavuzu'na yeni kayıt açılır ve SorumluDersKatalogu.okul_dersi
    bu kayda bağlanır; reddedilirse sadece bu öneri kaydı silinir (ders katalogda
    serbest metin ders_adi ile, Okul Ders Havuzu'na bağlanmadan kalmaya devam eder).
    """
    katalog = models.OneToOneField(
        SorumluDersKatalogu, on_delete=models.CASCADE,
        related_name="okul_dersi_onerisi", verbose_name="Ders",
    )
    olusturma_tarihi = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["katalog__ders_adi"]
        verbose_name = "Okul Ders Havuzu Önerisi"
        verbose_name_plural = "Okul Ders Havuzu Önerileri"

    def __str__(self):
        return f"{self.katalog.ders_adi} → Okul Ders Havuzu'na eklensin (onay bekliyor)"


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


class SorumluKomisyonUyesi(models.Model):
    """Bir oturumdaki ders için atanan iki komisyon üyesi.

    Takvim yeniden üretildiğinde (tarih/oturum/ders_adi aynı kalıyorsa) atamalar korunur.
    """
    sinav = models.ForeignKey(
        SorumluSinav, on_delete=models.CASCADE,
        related_name="komisyon_uyeler", verbose_name="Sınav",
    )
    tarih = models.DateField(verbose_name="Tarih")
    oturum_no = models.PositiveSmallIntegerField(verbose_name="Oturum No")
    ders_adi = models.CharField(max_length=200, verbose_name="Ders Adı")
    uye1 = models.ForeignKey(
        "okul.Personel", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+", verbose_name="1. Komisyon Üyesi",
    )
    uye2 = models.ForeignKey(
        "okul.Personel", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+", verbose_name="2. Komisyon Üyesi",
    )

    class Meta:
        unique_together = [("sinav", "tarih", "oturum_no", "ders_adi")]
        ordering = ["tarih", "oturum_no", "ders_adi"]
        verbose_name = "Komisyon Üyesi"
        verbose_name_plural = "Komisyon Üyeleri"

    def __str__(self):
        return f"{self.tarih:%d.%m.%Y} Ot.{self.oturum_no} – {self.ders_adi} — {self.uye1}, {self.uye2}"


class SorumluGozetmen(models.Model):
    """Bir oturumdaki her aktif salon için atanan gözetmen."""
    sinav = models.ForeignKey(
        SorumluSinav, on_delete=models.CASCADE,
        related_name="gozetmenler", verbose_name="Sınav",
    )
    tarih = models.DateField(verbose_name="Tarih")
    oturum_no = models.PositiveSmallIntegerField(verbose_name="Oturum No")
    salon = models.CharField(max_length=20, verbose_name="Salon")
    gozetmen = models.ForeignKey(
        "okul.Personel", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+", verbose_name="Gözetmen",
    )

    class Meta:
        unique_together = [("sinav", "tarih", "oturum_no", "salon")]
        ordering = ["tarih", "oturum_no", "salon"]
        verbose_name = "Gözetmen"
        verbose_name_plural = "Gözetmenler"

    def __str__(self):
        return (
            f"{self.tarih:%d.%m.%Y} Ot.{self.oturum_no} "
            f"– {self.salon} – {self.gozetmen}"
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
    salon          = models.CharField(max_length=20, verbose_name="Salon")
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


class OncekiDonem(models.Model):
    """Sisteme geçmeden önceki dönemlere ait sorumluluk sınavı kaydı."""
    sinav_adi        = models.CharField(max_length=200, verbose_name="Sınav Adı / Dönem Adı")
    egitim_yili      = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Eğitim-Öğretim Yılı",
    )
    donem_turu       = models.CharField(
        max_length=10,
        choices=DONEM_TURU_CHOICES,
        default="HAZIRAN",
        verbose_name="Dönem",
    )
    aciklama         = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")
    olusturma_tarihi = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ["-olusturma_tarihi"]
        verbose_name        = "Önceki Dönem"
        verbose_name_plural = "Önceki Dönemler"

    def __str__(self):
        egitim = str(self.egitim_yili) if self.egitim_yili_id else ""
        donem  = self.get_donem_turu_display()
        return f"{self.sinav_adi} ({egitim} {donem})".strip()


class OncekiDonemGorev(models.Model):
    """Önceki bir dönemde öğretmenin aldığı komisyon ve gözetmen görevi sayıları."""
    donem    = models.ForeignKey(
        OncekiDonem,
        on_delete=models.CASCADE,
        related_name="gorevler",
        verbose_name="Dönem",
    )
    personel = models.ForeignKey(
        "okul.Personel",
        on_delete=models.CASCADE,
        related_name="onceki_donem_gorevler",
        verbose_name="Personel",
    )
    komisyon = models.PositiveSmallIntegerField(default=0, verbose_name="Komisyon")
    gozetmen = models.PositiveSmallIntegerField(default=0, verbose_name="Gözetmen")

    class Meta:
        unique_together     = [("donem", "personel")]
        ordering            = ["personel__brans__ad", "personel__adi_soyadi"]
        verbose_name        = "Önceki Dönem Görevi"
        verbose_name_plural = "Önceki Dönem Görevleri"

    def __str__(self):
        return f"{self.donem} — {self.personel}: K={self.komisyon} G={self.gozetmen}"


class SorumluGorevMuafPersonel(models.Model):
    """Sorumluluk sınavlarında komisyon/gözetmen görevi verilmeyecek personel listesi.

    Tüm sorumluluk sınavları için geçerlidir (sınava özgü değildir).
    """
    personel = models.OneToOneField(
        "okul.Personel", on_delete=models.CASCADE,
        related_name="sorumluluk_gorev_muafiyeti", verbose_name="Personel",
    )
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")
    eklenme_tarihi = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["personel__adi_soyadi"]
        verbose_name = "Görev Muafiyeti"
        verbose_name_plural = "Görev Muafiyetleri"

    def __str__(self):
        return f"{self.personel} — Görev Muaf"