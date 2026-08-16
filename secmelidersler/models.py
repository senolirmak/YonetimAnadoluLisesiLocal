import re

from django.contrib.auth.models import User
from django.db import models

SINIF_SEVIYELERI = [(9, "9. Sınıf"), (10, "10. Sınıf"), (11, "11. Sınıf"), (12, "12. Sınıf")]

_VARSAYILAN_TOPLAM_SAAT = 40

_SAAT_EKI_RE = re.compile(r"\s*\(\d+\)\s*$")
_YILDIZ_EKI_RE = re.compile(r"\s*\*\s*$")


def normalize_ders_adi(ders_adi):
    """SecmeliDers.ders_adi saat eki taşır ("SEÇMELİ TARİH (1)") ve bazı
    OrtakDers adlarında sondaki '*' işareti bulunur; bu ekler olmadan başka
    sistemlerdeki (TTKB çizelgesi, sorumluluk ders kataloğu vb.) ders
    adlarıyla karşılaştırılabilecek şekilde temizler."""
    metin = _SAAT_EKI_RE.sub("", ders_adi)
    metin = _YILDIZ_EKI_RE.sub("", metin)
    return " ".join(metin.split())


# ---------------------------------------------------------------------------
# Eğitim-Öğretim Yılı yardımcı fonksiyonları
# ---------------------------------------------------------------------------

def get_aktif_egitim_yili():
    """OkulBilgi singleton'dan aktif eğitim-öğretim yılını döndürür."""
    from okul.models import OkulBilgi
    okul = OkulBilgi.objects.select_related("okul_egtyil").first()
    return okul.okul_egtyil if okul else None


# ---------------------------------------------------------------------------
# Sınıf Seviyesi Toplam Saat
# ---------------------------------------------------------------------------

class SinifSeviyeToplamSaat(models.Model):
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sinif_toplam_saatler",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    sinif_seviyesi = models.IntegerField(
        choices=SINIF_SEVIYELERI,
        verbose_name="Sınıf Seviyesi",
    )
    haftalik_toplam_saat = models.PositiveSmallIntegerField(
        default=_VARSAYILAN_TOPLAM_SAAT,
        verbose_name="Haftalık Toplam Saat",
        help_text="Bu sınıf seviyesindeki haftalık toplam ders saati (genellikle 40).",
    )

    class Meta:
        ordering = ["sinif_seviyesi"]
        unique_together = [("egitim_yili", "sinif_seviyesi")]
        verbose_name = "Sınıf Seviyesi Toplam Saat"
        verbose_name_plural = "Sınıf Seviyesi Toplam Saatler"

    def __str__(self):
        yil = f" [{self.egitim_yili}]" if self.egitim_yili else ""
        return f"{self.sinif_seviyesi}. Sınıf — {self.haftalik_toplam_saat} saat{yil}"


def get_toplam_saat(sinif_seviyesi, egitim_yili=None):
    """Sınıf seviyesi için haftalık toplam ders saatini döndürür. Kayıt yoksa 40."""
    if egitim_yili is None:
        egitim_yili = get_aktif_egitim_yili()
    try:
        return SinifSeviyeToplamSaat.objects.get(
            sinif_seviyesi=sinif_seviyesi,
            egitim_yili=egitim_yili,
        ).haftalik_toplam_saat
    except SinifSeviyeToplamSaat.DoesNotExist:
        return _VARSAYILAN_TOPLAM_SAAT


def get_toplam_saat_map(egitim_yili=None):
    """Tüm sınıf seviyeleri için {sinif_seviyesi: toplam_saat} sözlüğü. Eksik kayıtlar 40 varsayılanı alır."""
    if egitim_yili is None:
        egitim_yili = get_aktif_egitim_yili()
    result = {
        obj.sinif_seviyesi: obj.haftalik_toplam_saat
        for obj in SinifSeviyeToplamSaat.objects.filter(egitim_yili=egitim_yili)
    }
    for sv in (9, 10, 11, 12):
        result.setdefault(sv, _VARSAYILAN_TOPLAM_SAAT)
    return result


# ---------------------------------------------------------------------------
# Ortak (Zorunlu) Dersler
# ---------------------------------------------------------------------------

class OrtakDers(models.Model):
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ortak_dersler",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    sinif_seviyesi = models.IntegerField(choices=SINIF_SEVIYELERI, verbose_name="Sınıf Seviyesi")
    ders_adi = models.CharField(max_length=150, verbose_name="Ders Adı")
    haftalik_saat = models.PositiveSmallIntegerField(verbose_name="Haftalık Saat")
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    branslar = models.ManyToManyField(
        "okul.Brans",
        blank=True,
        related_name="ortak_dersler",
        verbose_name="Branş(lar)",
        help_text=(
            "Öğretmen ders yükü dağıtımında bu derse aynı branştaki öğretmenler önerilir. "
            "Bazı dersler (örn. GÖRSEL SANATLAR/MÜZİK) birden fazla branştan okutulabilir."
        ),
    )

    class Meta:
        ordering = ["sinif_seviyesi", "sira"]
        unique_together = [("egitim_yili", "sinif_seviyesi", "ders_adi")]
        verbose_name = "Ortak Ders"
        verbose_name_plural = "Ortak Dersler"

    def __str__(self):
        yil = f" [{self.egitim_yili}]" if self.egitim_yili else ""
        return f"{self.sinif_seviyesi}. Sınıf — {self.ders_adi}{yil}"


# ---------------------------------------------------------------------------
# Seçmeli Ders Grupları ve Dersler
# ---------------------------------------------------------------------------

class SecmeliDersGrubu(models.Model):
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="secmeli_ders_gruplari",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    sinif_seviyesi = models.IntegerField(choices=SINIF_SEVIYELERI, verbose_name="Sınıf Seviyesi")
    adi = models.CharField(max_length=100, verbose_name="Grup Adı")
    zorunlu_grup = models.BooleanField(
        default=False,
        verbose_name="Zorunlu Grup",
        help_text=(
            "9-10. sınıf: zorunlu grupların tamamından en az 1 ders seçilmeli. "
            "11-12. sınıf: zorunlu grupların en az ikisinden 1 ders seçilmeli."
        ),
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        ordering = ["sinif_seviyesi", "sira"]
        unique_together = [("egitim_yili", "sinif_seviyesi", "adi")]
        verbose_name = "Seçmeli Ders Grubu"
        verbose_name_plural = "Seçmeli Ders Grupları"

    def __str__(self):
        yil = f" [{self.egitim_yili}]" if self.egitim_yili else ""
        return f"{self.sinif_seviyesi}. Sınıf — {self.adi}{yil}"


class SecmeliDers(models.Model):
    grup = models.ForeignKey(
        SecmeliDersGrubu,
        on_delete=models.CASCADE,
        related_name="dersler",
        verbose_name="Grup",
    )
    ders_adi = models.CharField(max_length=200, verbose_name="Ders Adı")
    saat_secenekleri = models.CharField(
        max_length=50,
        verbose_name="Saat Seçenekleri",
        help_text="Virgülle ayrılmış saat seçenekleri. Tek değer sabit saati gösterir. Örn: '4' veya '2,4' veya '1,2,3'",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    branslar = models.ManyToManyField(
        "okul.Brans",
        blank=True,
        related_name="secmeli_dersler",
        verbose_name="Branş(lar)",
        help_text=(
            "Öğretmen ders yükü dağıtımında bu derse aynı branştaki öğretmenler önerilir. "
            "Bazı dersler (örn. GÖRSEL SANATLAR/MÜZİK) birden fazla branştan okutulabilir."
        ),
    )

    class Meta:
        ordering = ["sira"]
        verbose_name = "Seçmeli Ders"
        verbose_name_plural = "Seçmeli Dersler"

    def __str__(self):
        return f"{self.ders_adi} ({self.saat_secenekleri}s)"

    @property
    def saat_listesi(self):
        return [int(s.strip()) for s in self.saat_secenekleri.split(",") if s.strip().isdigit()]

    @property
    def sabit_saat(self):
        lst = self.saat_listesi
        return lst[0] if len(lst) == 1 else None

    @property
    def secimli_saat(self):
        return len(self.saat_listesi) > 1


# ---------------------------------------------------------------------------
# Alan
# ---------------------------------------------------------------------------

class Alan(models.Model):
    SINIF_CHOICES = [(9, "9. Sınıf"), (10, "10. Sınıf"), (11, "11. Sınıf"), (12, "12. Sınıf")]
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alanlar",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    sinif_seviyesi = models.IntegerField(choices=SINIF_CHOICES, verbose_name="Sınıf Seviyesi")
    adi = models.CharField(max_length=50, verbose_name="Alan Adı")
    dersler = models.ManyToManyField(
        SecmeliDers,
        through="AlanDers",
        blank=True,
        related_name="alanlar",
        verbose_name="Seçmeli Dersler",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")

    class Meta:
        ordering = ["sinif_seviyesi", "sira"]
        unique_together = [("egitim_yili", "sinif_seviyesi", "adi")]
        verbose_name = "Alan"
        verbose_name_plural = "Alanlar"

    def __str__(self):
        yil = f" [{self.egitim_yili}]" if self.egitim_yili else ""
        return f"{self.sinif_seviyesi}. Sınıf — {self.adi}{yil}"


class AlanDers(models.Model):
    alan = models.ForeignKey(Alan, on_delete=models.CASCADE, related_name="alan_dersler")
    ders = models.ForeignKey(SecmeliDers, on_delete=models.CASCADE, related_name="alan_dersler")
    secilen_saat = models.PositiveSmallIntegerField(verbose_name="Seçilen Saat")

    class Meta:
        unique_together = [("alan", "ders")]
        verbose_name = "Alan Dersi"
        verbose_name_plural = "Alan Dersleri"

    def __str__(self):
        return f"{self.alan.adi} — {self.ders.ders_adi} ({self.secilen_saat}s)"


class SecmeliDersBransPaylasimi(models.Model):
    """Birden fazla branşa atanmış bir SecmeliDers'in (bkz. `SecmeliDers.branslar`),
    belirli bir Alan'da (bu `AlanDers`) okutulduğu GERÇEK şubelerin, branşlar
    arasında NASIL PAYLAŞTIRILDIĞINI tutar.

    Gizli hata: bir ders birden fazla branşa atanmışsa (örn. "TÜRK SOSYAL
    HAYATINDA AİLE" hem Tarih hem Felsefe'ye atanmış), `services/ders_yuku.
    hesapla()` varsayılan olarak TAM saati HER İKİ branşa da ekler
    (branş↔ders eşleştirmesinde saatler paylaştırılmaz kuralı) — bu, aynı
    şubelerin saatinin iki (veya daha fazla) kez sayılması demektir. Bu model
    bunu çözer: bir AlanDers için en az bir `SecmeliDersBransPaylasimi` kaydı
    varsa, o AlanDers'in saati artık her branşa TAM olarak değil, burada
    belirtilen GERÇEK şube alt kümesi kadar paylaştırılarak hesaba katılır.

    İstisna: bazı ZORUNLU (Ortak) dersler de aynı çift-sayım hatasına
    sahiptir — örn. 12. sınıf "BEDEN EĞİTİMİ VE SPOR/GÖRSEL SANATLAR/MÜZİK"
    dersi üç branşa birden atanmıştır, ama gerçekte her öğrenci bunlardan
    yalnızca birini seçer. `services/ders_yuku.BRANS_PAYLASIM_ISTISNA_ORTAK_DERSLER`
    içinde adı geçen `OrtakDers` kayıtları için bu paylaşım `alan_ders` yerine
    `ortak_ders` alanı üzerinden tutulur — bir kayıtta ikisinden yalnızca biri
    dolu olur.
    """

    alan_ders = models.ForeignKey(
        AlanDers,
        on_delete=models.CASCADE,
        related_name="brans_paylasimlari",
        verbose_name="Alan Dersi",
        null=True,
        blank=True,
    )
    ortak_ders = models.ForeignKey(
        OrtakDers,
        on_delete=models.CASCADE,
        related_name="brans_paylasimlari",
        verbose_name="Ortak Ders (istisna)",
        null=True,
        blank=True,
        help_text="Yalnızca BRANS_PAYLASIM_ISTISNA_ORTAK_DERSLER'de tanımlı istisna Ortak Dersler için kullanılır.",
    )
    brans = models.ForeignKey(
        "okul.Brans", on_delete=models.CASCADE, related_name="+", verbose_name="Branş",
    )
    subeler = models.CharField(
        max_length=100,
        verbose_name="Şubeler",
        help_text="Bu branşa ayrılan gerçek şubeler, virgülle ayrılmış. Örn: A,B",
    )

    class Meta:
        db_table = "secmelidersler_secmeli_ders_brans_paylasimi"
        unique_together = [("alan_ders", "brans"), ("ortak_ders", "brans")]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(alan_ders__isnull=False, ortak_ders__isnull=True)
                    | models.Q(alan_ders__isnull=True, ortak_ders__isnull=False)
                ),
                name="secmelidersler_brans_paylasimi_tek_kaynak",
            ),
        ]
        verbose_name = "Seçmeli Ders Branş Paylaşımı"
        verbose_name_plural = "Seçmeli Ders Branş Paylaşımları"

    def __str__(self):
        kaynak = self.alan_ders or self.ortak_ders
        return f"{kaynak} — {self.brans.ad}: {self.subeler}"

    @property
    def sube_listesi(self):
        return [s.strip().upper() for s in self.subeler.split(",") if s.strip()]

    @property
    def sube_sayisi(self):
        return len(self.sube_listesi)

    @property
    def etiket_listesi(self):
        """`sube_listesi` ile aynı sırada, kullanıcıya gösterilecek okunur
        etiketler — bölünmemiş bir şube için düz harf ('A'), bölünmüş bir
        parça için 'A·2s' gibi saat ekiyle (bkz. SecmeliDersSubeBolunmesi;
        token biçimi orada da ayrıca ayrıştırılır — bkz.
        `services.ders_yuku._sube_token_etiket`)."""
        sonuc = []
        for token in self.sube_listesi:
            parcalar = token.split("#")
            if len(parcalar) == 3:
                harf, _sira, saat = parcalar
                sonuc.append(f"{harf}·{saat}s")
            else:
                sonuc.append(token)
        return sonuc

    @property
    def rozetler(self):
        """`sube_listesi`/`etiket_listesi`yi şablonun TEK bir döngüde
        kullanabileceği şekilde birleştirir: [{"sube": token, "etiket": str,
        "bolunmus": bool}, ...]. `bolunmus=False` olan rozetler için "Böl"
        düğmesi gösterilir (zaten bölünmüş bir parça yeniden bölünemez)."""
        return [
            {"sube": token, "etiket": etiket, "bolunmus": "#" in token}
            for token, etiket in zip(self.sube_listesi, self.etiket_listesi)
        ]


class SecmeliDersSubeBolunmesi(models.Model):
    """Bir (AlanDers|OrtakDers, şube) çiftinin ders saatinin BİRDEN FAZLA
    PARÇAYA bölündüğünü tutar — bkz. `services/ders_yuku` modül docstring'i
    "Şube Bölme" bölümü. Bölünme YOKSA (bu tabloda kayıt yoksa) şube TEK PARÇA
    (tüm ders saati) olarak davranır; `SecmeliDersBransPaylasimi` ile eski
    davranışla tam uyumludur.

    İki kullanım biçimi vardır (ikisi de aynı mekanizmayı — parça listesi —
    kullanır, aralarındaki fark yalnızca parçaların TOPLAMIdır):
      - GERÇEK SAAT BÖLÜNMESİ: parçaların toplamı dersin toplam saatine
        EŞİTTİR (örn. 3 saatlik "HEDEF TEMELLİ DESTEK EĞİTİMİ" için "1,2" ya
        da "1,1,1") — her parça FARKLI bir branşa, kendi saatiyle paylaştırılır.
      - İKİZ (tam kopya): her parça dersin TAM saatine EŞİTTİR (örn. 2 saatlik
        "BEDEN EĞİTİMİ VE SPOR/GÖRSEL SANATLAR/MÜZİK" için "2,2,2") — aynı
        şubenin farklı öğrencileri AYNI saatte FARKLI branşlarda ders
        gördüğünden (paralel şube-içi seçim) her branş TAM saat alır;
        parçaların toplamı dersin saatini AŞAR — bu durumda normaldir.
    """

    alan_ders = models.ForeignKey(
        AlanDers,
        on_delete=models.CASCADE,
        related_name="sube_bolunmeleri",
        verbose_name="Alan Dersi",
        null=True,
        blank=True,
    )
    ortak_ders = models.ForeignKey(
        OrtakDers,
        on_delete=models.CASCADE,
        related_name="sube_bolunmeleri",
        verbose_name="Ortak Ders (istisna)",
        null=True,
        blank=True,
    )
    sube = models.CharField(max_length=2, verbose_name="Şube")
    parcalar = models.CharField(
        max_length=60,
        verbose_name="Saat Parçaları",
        help_text="Virgülle ayrılmış saat değerleri. Örn: 1,2 ya da 2,2,2",
    )

    class Meta:
        db_table = "secmelidersler_secmeli_ders_sube_bolunmesi"
        unique_together = [("alan_ders", "sube"), ("ortak_ders", "sube")]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(alan_ders__isnull=False, ortak_ders__isnull=True)
                    | models.Q(alan_ders__isnull=True, ortak_ders__isnull=False)
                ),
                name="secmelidersler_sube_bolunmesi_tek_kaynak",
            ),
        ]
        verbose_name = "Seçmeli Ders Şube Bölünmesi"
        verbose_name_plural = "Seçmeli Ders Şube Bölünmeleri"

    def __str__(self):
        kaynak = self.alan_ders or self.ortak_ders
        return f"{kaynak} — {self.sube}: {self.parcalar}"

    @property
    def parca_listesi(self):
        """Saat parçalarını (pozitif tamsayı) sırasıyla döner; geçersiz/boş
        girişler atlanır."""
        sonuc = []
        for p in self.parcalar.split(","):
            p = p.strip()
            if not p:
                continue
            try:
                deger = int(p)
            except ValueError:
                continue
            if deger > 0:
                sonuc.append(deger)
        return sonuc


class AlanSubeAtama(models.Model):
    """Bir Alan'ın (bkz. Alan modeli) ders yükü hesabında kullanılacak şube
    listesinin ELLE atanmış hâli.

    Ders yükü raporu (services/ders_yuku.py) 11-12. sınıf Alanları için şube
    sayısını `ders_dagilimi.plan_sinif_dagilimi_gecmis` ile OTOMATİK tespit
    eder — ama bu, öğrencilerin GERÇEK seçimlerinin hangi Alan/AlanDers
    kataloğuna (hangi eğitim-öğretim yılına) bağlı olduğuna dayanır ve her
    zaman doğru sonuç vermeyebilir (örn. henüz seçim yapılmamış yeni bir yıl,
    veya kohort eşleştirmesinin belirsiz kaldığı durumlar). Bu kayıt varsa
    otomatik tespitin ÜZERİNE YAZAR.
    """

    alan = models.OneToOneField(
        Alan, on_delete=models.CASCADE, related_name="sube_atamasi", verbose_name="Alan"
    )
    subeler = models.CharField(
        max_length=100,
        verbose_name="Şubeler",
        help_text="Virgülle ayrılmış şube harfleri. Örn: A,B,C",
    )
    guncelleme_tarihi = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")

    class Meta:
        db_table = "secmelidersler_alan_sube_atama"
        verbose_name = "Alan Şube Ataması"
        verbose_name_plural = "Alan Şube Atamaları"

    def __str__(self):
        return f"{self.alan} — {self.subeler}"

    @property
    def sube_listesi(self):
        return [s.strip().upper() for s in self.subeler.split(",") if s.strip()]

    @property
    def sube_sayisi(self):
        return len(self.sube_listesi)


class YoneticiZorunluDersYuku(models.Model):
    """Okul Müdürü / Müdür Yardımcısı gibi yönetici görevindeki personelin
    haftalık ZORUNLU ders yükü (saat) — idari görevleri nedeniyle normal
    öğretmenlerden çok daha düşük olan azaltılmış ders yükümlülüğü.

    Branş bazlı norm kadro hesabında (services/ders_yuku.py `hesapla()`) bu
    saat, ilgili branşın toplam ders yükünden DÜŞÜLÜP norm ondan sonra
    hesaplanır — aksi hâlde yönetici "1 mevcut" olarak sayılırken aslında
    yalnızca birkaç saat ders okuttuğu hâlde tam kapasiteli bir öğretmenmiş
    gibi normu dengelermiş yanıltıcı bir izlenim oluşurdu.
    """

    personel = models.OneToOneField(
        "okul.Personel",
        on_delete=models.CASCADE,
        related_name="zorunlu_ders_yuku",
        verbose_name="Personel",
    )
    saat = models.PositiveSmallIntegerField(
        default=0, verbose_name="Zorunlu Ders Yükü (Saat)"
    )
    guncelleme_tarihi = models.DateTimeField(auto_now=True, verbose_name="Güncellenme Tarihi")

    class Meta:
        db_table = "secmelidersler_yonetici_zorunlu_ders_yuku"
        verbose_name = "Yönetici Zorunlu Ders Yükü"
        verbose_name_plural = "Yönetici Zorunlu Ders Yükleri"

    def __str__(self):
        return f"{self.personel.adi_soyadi} — {self.saat}s"


class NormKadroArsivi(models.Model):
    """Branş norm kadro hesabının belirli bir TARİHTE alınmış, DEĞİŞMEZ anlık
    görüntüsü (snapshot).

    Norm ile ilgili güncellemeler (Alan Şube Ataması, Yönetici Zorunlu Ders
    Yükü, branş/ders atamaları vb.) bittiğinde bu arşiv oluşturulur; sonradan
    alttaki veriler (ders programı, personel, şube sayıları) değişse bile
    arşivlenen satırlar SABİT kalır — "o tarihte norm hesabı böyleydi" diye
    tarihe damgalanmış bir kayıt işlevi görür. `services/ders_yuku.arsivle()`
    ile oluşturulur; CRUD arayüzü yalnızca oluşturma ve listeleme sağlar,
    düzenleme/silme YOKTUR (bkz. views.py).
    """

    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        related_name="norm_kadro_arsivleri",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    tarih = models.DateTimeField(auto_now_add=True, verbose_name="Arşivlenme Tarihi")
    olusturan = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Oluşturan",
    )

    class Meta:
        db_table = "secmelidersler_norm_kadro_arsivi"
        ordering = ["-tarih"]
        verbose_name = "Norm Kadro Arşivi"
        verbose_name_plural = "Norm Kadro Arşivleri"

    def __str__(self):
        return f"{self.egitim_yili} — {self.tarih:%d.%m.%Y %H:%M}"


class NormKadroArsiviSatiri(models.Model):
    """`NormKadroArsivi`nin tek bir branşa ait donmuş satırı — bkz. o modelin
    docstring'i. Alanlar `services/ders_yuku.hesapla()`nın döndürdüğü sözlükle
    birebir eşleşir."""

    arsiv = models.ForeignKey(
        NormKadroArsivi, on_delete=models.CASCADE, related_name="satirlar",
        verbose_name="Arşiv",
    )
    brans = models.ForeignKey(
        "okul.Brans", on_delete=models.PROTECT, related_name="+", verbose_name="Branş",
    )
    ortak_saat = models.PositiveIntegerField(default=0, verbose_name="Ortak Saat")
    secmeli_saat = models.PositiveIntegerField(default=0, verbose_name="Seçmeli Saat")
    toplam_saat = models.PositiveIntegerField(default=0, verbose_name="Toplam Saat")
    yonetici_dusum_saat = models.PositiveIntegerField(default=0, verbose_name="Yönetici Düşümü")
    norm_hesap_saati = models.PositiveIntegerField(default=0, verbose_name="Norm Hesap Saati")
    norm_kadro = models.PositiveSmallIntegerField(default=0, verbose_name="Norm Kadro")
    mevcut = models.PositiveSmallIntegerField(default=0, verbose_name="Mevcut")
    fazla = models.PositiveSmallIntegerField(default=0, verbose_name="Fazla")
    eksik = models.PositiveSmallIntegerField(default=0, verbose_name="Eksik")

    class Meta:
        db_table = "secmelidersler_norm_kadro_arsivi_satiri"
        unique_together = [("arsiv", "brans")]
        ordering = ["brans__ad"]
        verbose_name = "Norm Kadro Arşivi Satırı"
        verbose_name_plural = "Norm Kadro Arşivi Satırları"

    def __str__(self):
        return f"{self.arsiv} — {self.brans.ad}"


# ---------------------------------------------------------------------------
# Katalog (global havuz — EÖY bağımsız)
# ---------------------------------------------------------------------------

class OrtakDersHavuzu(models.Model):
    ders_adi = models.CharField(max_length=200, unique=True, verbose_name="Ders Adı")
    derssaati = models.CharField(
        max_length=50,
        default="",
        verbose_name="Ders Saati",
        help_text="Virgülle ayrılmış saat seçenekleri. Örn: '4' veya '2,4' veya '1,2,3'",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    branslar = models.ManyToManyField(
        "okul.Brans",
        blank=True,
        related_name="ortak_ders_havuzu",
        verbose_name="Branş(lar)",
        help_text=(
            "Öğretmen ders yükü dağıtımında bu derse aynı branştaki öğretmenler önerilir. "
            "Bazı dersler birden fazla branştan okutulabilir."
        ),
    )

    class Meta:
        ordering = ["sira", "ders_adi"]
        verbose_name = "Ortak Ders (Havuz)"
        verbose_name_plural = "Ortak Ders Havuzu"

    def __str__(self):
        return self.ders_adi


class SecmeliDersHavuzu(models.Model):
    ders_adi = models.CharField(max_length=200, unique=True, verbose_name="Ders Adı")
    derssaati = models.CharField(
        max_length=50,
        default="",
        verbose_name="Ders Saati",
        help_text="Virgülle ayrılmış saat seçenekleri. Örn: '4' veya '2,4' veya '1,2,3'",
    )
    secimsayisi = models.PositiveSmallIntegerField(
        default=1,
        verbose_name="Seçim Sayısı",
        help_text="Öğrencinin bu dersi kaç defa seçebileceği (genellikle 1).",
    )
    sira = models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    branslar = models.ManyToManyField(
        "okul.Brans",
        blank=True,
        related_name="secmeli_ders_havuzu",
        verbose_name="Branş(lar)",
        help_text=(
            "Öğretmen ders yükü dağıtımında bu derse aynı branştaki öğretmenler önerilir. "
            "Bazı dersler birden fazla branştan okutulabilir."
        ),
    )

    class Meta:
        ordering = ["sira", "ders_adi"]
        verbose_name = "Seçmeli Ders (Havuz)"
        verbose_name_plural = "Seçmeli Ders Havuzu"

    def __str__(self):
        return self.ders_adi


# ---------------------------------------------------------------------------
# Sınıf Tekrarı
# ---------------------------------------------------------------------------

class OgrenciSinifTekrari(models.Model):
    ogrenci = models.OneToOneField(
        "ogrenci.Ogrenci",
        on_delete=models.CASCADE,
        related_name="sinif_tekrari",
        verbose_name="Öğrenci",
    )
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sinif_tekrarilar",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sınıf Tekrarı"
        verbose_name_plural = "Sınıf Tekrarları"

    def __str__(self):
        return f"{self.ogrenci} — Sınıf Tekrarı"


# ---------------------------------------------------------------------------
# Tasdikname (Okuma Hakkı Biten Öğrenciler)
# ---------------------------------------------------------------------------

class OgrenciTasdikname(models.Model):
    ogrenci = models.OneToOneField(
        "ogrenci.Ogrenci",
        on_delete=models.CASCADE,
        related_name="tasdikname",
        verbose_name="Öğrenci",
    )
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tasdiknameler",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    tarih = models.DateField(null=True, blank=True, verbose_name="Tasdikname Tarihi")
    aciklama = models.CharField(max_length=300, blank=True, verbose_name="Açıklama")
    olusturma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tasdikname"
        verbose_name_plural = "Tasdiknameler"

    def __str__(self):
        return f"{self.ogrenci} — Tasdikname"


# ---------------------------------------------------------------------------
# Öğrenci Dönem Ağırlıklı Ortalaması
# ---------------------------------------------------------------------------

class OgrenciOrtalama(models.Model):
    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        on_delete=models.CASCADE,
        related_name="ortalamalar",
        verbose_name="Öğrenci",
    )
    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ogrenci_ortalamalar",
        verbose_name="Eğitim-Öğretim Yılı",
    )
    a_ortalama = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Ağırlıklı Ortalama",
    )
    guncelleme = models.DateTimeField(auto_now=True, verbose_name="Güncellenme")

    class Meta:
        unique_together = [("ogrenci", "egitim_yili")]
        ordering = ["ogrenci__okulno"]
        verbose_name = "Öğrenci Ortalaması"
        verbose_name_plural = "Öğrenci Ortalamaları"

    def __str__(self):
        return f"{self.ogrenci} — {self.a_ortalama}"
