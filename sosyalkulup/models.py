"""
sosyalkulup — Öğrenci sosyal kulüpleri, danışman öğretmenler ve kulüp üyelikleri.

- `SosyalKulup` kulüp tanımıdır (katalog); eğitim yılından bağımsızdır, her yıl yeniden
  girilmez.
- `KulupDanisman` ve `KulupUyelik` yıllık kayıtlardır ve bir eğitim-öğretim yılıyla
  damgalanır. Yıl verilmezse kayıt anında `OkulBilgi`'deki aktif yıl yazılır; böylece
  geçmiş yılların danışman/üye listeleri korunur.
"""

from django.core.exceptions import ValidationError
from django.db import models


class SosyalKulup(models.Model):
    ad = models.CharField(max_length=150, unique=True, verbose_name="Kulüp Adı")
    aciklama = models.TextField(blank=True, verbose_name="Açıklama")
    aktif = models.BooleanField(
        default=True,
        verbose_name="Aktif",
        help_text="Pasif kulüpler yeni danışman/üye atamalarında listelenmez; "
        "geçmiş kayıtları korunur.",
    )

    class Meta:
        db_table = "sosyal_kulup"
        verbose_name = "Sosyal Kulüp"
        verbose_name_plural = "Sosyal Kulüpler"
        ordering = ["ad"]

    def __str__(self):
        return self.ad


class EgitimYiliDamgali(models.Model):
    """Kaydı bir eğitim-öğretim yılına bağlayan ortak alan.

    `egitim_yili` boş bırakılırsa `clean()`/`save()` aktif eğitim yılını yazar. Aktif yıl
    tanımlı değilse (Okul Bilgisi yapılandırılmamışsa) kayıt reddedilir.
    """

    egitim_yili = models.ForeignKey(
        "okul.EgitimOgretimYili",
        on_delete=models.PROTECT,
        blank=True,
        related_name="%(class)s_kayitlari",
        verbose_name="Eğitim-Öğretim Yılı",
        help_text="Boş bırakılırsa aktif eğitim-öğretim yılı kullanılır.",
    )
    olusturma = models.DateTimeField(auto_now_add=True, verbose_name="Kayıt Tarihi")

    class Meta:
        abstract = True

    def _egitim_yilini_damgala(self):
        if self.egitim_yili_id is None:
            from okul.utils import get_aktif_egitim_yili

            yil = get_aktif_egitim_yili()
            if yil is None:
                raise ValidationError(
                    {"egitim_yili": "Aktif eğitim-öğretim yılı tanımlı değil; "
                     "önce Okul Bilgisi'nden aktif yılı seçin."}
                )
            self.egitim_yili = yil

    def clean(self):
        super().clean()
        self._egitim_yilini_damgala()

    def save(self, *args, **kwargs):
        self._egitim_yilini_damgala()
        super().save(*args, **kwargs)


class KulupDanisman(EgitimYiliDamgali):
    kulup = models.ForeignKey(
        SosyalKulup,
        on_delete=models.PROTECT,
        related_name="danismanlar",
        verbose_name="Kulüp",
    )
    ogretmen = models.ForeignKey(
        "okul.Personel",
        on_delete=models.PROTECT,
        related_name="kulup_danismanliklari",
        verbose_name="Danışman Öğretmen",
    )

    class Meta:
        db_table = "sosyal_kulup_danisman"
        verbose_name = "Kulüp Danışman Öğretmeni"
        verbose_name_plural = "Kulüp Danışman Öğretmenleri"
        ordering = ["-egitim_yili__egitim_baslangic", "kulup__ad"]
        constraints = [
            models.UniqueConstraint(
                fields=["egitim_yili", "kulup", "ogretmen"],
                name="kulup_danisman_yil_tekil",
            ),
        ]

    def __str__(self):
        return f"{self.kulup} — {self.ogretmen} ({self.egitim_yili})"


class KulupUyelik(EgitimYiliDamgali):
    GOREV_UYE = "uye"
    GOREV_CHOICES = (
        ("baskan", "Başkan"),
        ("baskan_yardimcisi", "Başkan Yardımcısı"),
        ("sekreter", "Sekreter"),
        ("sayman", "Sayman"),
        (GOREV_UYE, "Üye"),
    )

    kulup = models.ForeignKey(
        SosyalKulup,
        on_delete=models.PROTECT,
        related_name="uyelikler",
        verbose_name="Kulüp",
    )
    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        on_delete=models.CASCADE,
        related_name="kulup_uyelikleri",
        verbose_name="Öğrenci",
    )
    gorev = models.CharField(
        max_length=20,
        choices=GOREV_CHOICES,
        default=GOREV_UYE,
        verbose_name="Kulüpteki Görevi",
    )

    class Meta:
        db_table = "sosyal_kulup_uyelik"
        verbose_name = "Kulüp Üyeliği"
        verbose_name_plural = "Kulüp Üyelikleri"
        ordering = ["-egitim_yili__egitim_baslangic", "kulup__ad", "ogrenci__sinif",
                    "ogrenci__sube", "ogrenci__okulno"]
        constraints = [
            # Bir öğrenci bir eğitim yılında yalnızca bir kulübe üye olabilir.
            models.UniqueConstraint(
                fields=["egitim_yili", "ogrenci"],
                name="kulup_uyelik_ogrenci_yil_tekil",
            ),
        ]

    def __str__(self):
        return f"{self.ogrenci} — {self.kulup} ({self.egitim_yili})"
