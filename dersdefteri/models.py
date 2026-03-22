from django.db import models
from django.utils import timezone


class DersDefteri(models.Model):
    """
    Bir öğretmenin belirli bir tarih, sınıf ve ders saatine ait ders kaydı.

    - ogretmen       : Girişi yapan öğretmen (NobetPersonel)
    - tarih          : Dersin tarihi (varsayılan: bugün)
    - sinif_sube     : Dersin verildiği sınıf (NobetDersProgrami'nden otomatik doldurulabilir)
    - ders_adi       : Ders adı
    - ders_saati     : Kaçıncı ders saati (1, 2, 3…)
    - giris_saat     : Ders başlangıç saati
    - cikis_saat     : Ders bitiş saati
    - icerik         : Ders planı / işlenen konu
    - devamsiz_ogrenciler : O ders saatinde devamsız olan sınıf öğrencileri (M2M)
    """

    ogretmen = models.ForeignKey(
        "nobet.NobetPersonel",
        on_delete=models.CASCADE,
        related_name="ders_defterleri",
        verbose_name="Öğretmen",
    )
    tarih = models.DateField(
        default=timezone.localdate,
        verbose_name="Tarih",
    )
    sinif_sube = models.ForeignKey(
        "nobet.SinifSube",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ders_defterleri",
        verbose_name="Sınıf / Şube",
    )
    ders_adi = models.CharField(max_length=100, verbose_name="Ders Adı")
    ders_saati = models.PositiveSmallIntegerField(verbose_name="Ders Saati No")
    giris_saat = models.TimeField(verbose_name="Giriş Saati")
    cikis_saat = models.TimeField(verbose_name="Çıkış Saati")
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
        ordering = ["-tarih", "ders_saati"]
        # Aynı öğretmen, aynı gün, aynı sınıfta, aynı ders saatine tek kayıt
        unique_together = ("ogretmen", "tarih", "sinif_sube", "ders_saati")

    def __str__(self):
        sinif = str(self.sinif_sube) if self.sinif_sube else "–"
        return f"{self.ogretmen.adi_soyadi} | {self.tarih} | {sinif} | {self.ders_saati}. Ders"
