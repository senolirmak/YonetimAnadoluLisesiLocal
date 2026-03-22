from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class OgrenciCagri(models.Model):
    SERVIS_REHBERLIK = "rehberlik"
    SERVIS_DISIPLIN = "disiplin"
    SERVIS_MUDURIYETCAGRI = "muduriyetcagri"
    SERVIS_CHOICES = [
        (SERVIS_REHBERLIK, "Rehberlik"),
        (SERVIS_DISIPLIN, "Disiplin"),
        (SERVIS_MUDURIYETCAGRI, "Müdüriyet"),
    ]

    servis = models.CharField(
        max_length=20,
        choices=SERVIS_CHOICES,
        db_index=True,
        verbose_name="Servis",
    )
    kayit_eden = models.ForeignKey(
        "nobet.NobetPersonel",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Kaydeden (Personel)",
    )
    kayit_eden_kullanici = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Kaydeden (Kullanıcı)",
    )
    ogrenci = models.ForeignKey(
        "ogrenci.Ogrenci",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Öğrenci",
    )
    tarih = models.DateField(verbose_name="Tarih")
    ders_saati = models.IntegerField(null=True, blank=True, verbose_name="Ders Saati")
    ders_adi = models.CharField(max_length=100, blank=True, verbose_name="Ders Adı")
    ogretmen_adi = models.CharField(max_length=100, blank=True, verbose_name="Dersin Öğretmeni")
    cagri_metni = models.TextField(blank=True, verbose_name="Çağrı Metni")

    # Görüşme bağlantıları (servis'e göre biri dolu olur)
    gorusme_rehberlik = models.ForeignKey(
        "rehberlik.Gorusme",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Rehberlik Görüşmesi",
    )
    gorusme_disiplin = models.ForeignKey(
        "disiplin.DisiplinGorusme",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Disiplin Görüşmesi",
    )
    gorusme_muduriyetcagri = models.ForeignKey(
        "muduriyetcagri.MuduriyetGorusme",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Müdüriyet Görüşmesi",
    )

    olusturma_zamani = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cagri_ogrencicagri"
        ordering = ["-tarih", "ders_saati"]
        verbose_name = "Öğrenci Çağrısı"
        verbose_name_plural = "Öğrenci Çağrıları"

    def __str__(self):
        ogr = str(self.ogrenci) if self.ogrenci else "—"
        return f"{self.servis} | {self.tarih} | {ogr}"

    @property
    def kayit_eden_adi(self):
        if self.kayit_eden:
            return self.kayit_eden.adi_soyadi
        if self.kayit_eden_kullanici:
            full = self.kayit_eden_kullanici.get_full_name()
            return full if full else self.kayit_eden_kullanici.username
        return "—"

    @property
    def aktif_gorusme(self):
        """Servise ait görüşme nesnesini döner."""
        if self.servis == self.SERVIS_REHBERLIK:
            return self.gorusme_rehberlik
        if self.servis == self.SERVIS_DISIPLIN:
            return self.gorusme_disiplin
        if self.servis == self.SERVIS_MUDURIYETCAGRI:
            return self.gorusme_muduriyetcagri
        return None
