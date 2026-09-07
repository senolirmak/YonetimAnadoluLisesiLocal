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
