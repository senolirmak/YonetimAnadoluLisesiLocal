from django.db import models
from django.utils import timezone


class DersDefteri(models.Model):
    """
    Bir öğretmenin belirli bir tarih, sınıf ve ders saatine ait ders kaydı.

    - ogretmen       : Girişi yapan öğretmen (Personel)
    - tarih          : Dersin tarihi (varsayılan: bugün)
    - sinif_sube     : Dersin verildiği sınıf (DersProgrami'nden otomatik doldurulabilir)
    - ders_adi       : Ders adı
    - ders_saati     : DersSaatleri FK (kaçıncı ders saati)
    - icerik         : Ders planı / işlenen konu
    - devamsiz_ogrenciler : O ders saatinde devamsız olan sınıf öğrencileri (M2M)
    """

    ogretmen = models.ForeignKey(
        "okul.Personel",
        on_delete=models.CASCADE,
        related_name="ders_defterleri",
        verbose_name="Öğretmen",
    )
    tarih = models.DateField(
        default=timezone.localdate,
        verbose_name="Tarih",
    )
    sinif_sube = models.ForeignKey(
        "okul.SinifSube",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ders_defterleri",
        verbose_name="Sınıf / Şube",
    )
    ders_adi = models.CharField(max_length=100, verbose_name="Ders Adı")
    ders_saati = models.ForeignKey(
        "okul.DersSaatleri",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dersdefteri",
        verbose_name="Ders Saati",
    )
    icerik = models.TextField(blank=True, verbose_name="İşlenen Konu / Ders Planı")
    devamsiz_ogrenciler = models.ManyToManyField(
        "ogrenci.Ogrenci",
        blank=True,
        related_name="dersdefteri_kayitlari",
        verbose_name="Devamsız Öğrenciler",
    )
    olusturma_zamani = models.DateTimeField(auto_now_add=True)
    guncelleme_zamani = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dersdefteri"
        verbose_name = "Ders Defteri Kaydı"
        verbose_name_plural = "Ders Defteri"
        ordering = ["-tarih", "ders_saati__derssaati_no"]
        # Aynı öğretmen, aynı gün, aynı sınıfta, aynı ders saatine tek kayıt
        unique_together = ("ogretmen", "tarih", "sinif_sube", "ders_saati")

    def __str__(self):
        sinif = str(self.sinif_sube) if self.sinif_sube else "–"
        ds_no = self.ders_saati.derssaati_no if self.ders_saati else "?"
        return f"{self.ogretmen.adi_soyadi} | {self.tarih} | {sinif} | {ds_no}. Ders"

    # ------------------------------------------------------------------
    # Backward-compat properties
    # ------------------------------------------------------------------

    @property
    def giris_saat(self):
        return self.ders_saati.derssaati_baslangic if self.ders_saati else None

    @property
    def cikis_saat(self):
        return self.ders_saati.derssaati_bitis if self.ders_saati else None
