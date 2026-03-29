"""
OgrenciCagri ve Duyuru modelleri kaydedildiğinde
ilgili sınıfın tahtasına otomatik bildirim gönderir.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


# ──────────────────────────────────────────────
# Öğrenci Çağrısı sinyali
# ──────────────────────────────────────────────

@receiver(post_save, sender="cagri.OgrenciCagri")
def cagri_bildirimi_gonder(sender, instance, created, **kwargs):
    if not created:
        return
    if not instance.ogrenci:
        return

    from bildirim_gonderici.services import sinif_bildirimi_gonder
    from bildirim_gonderici.models import BildirimLog
    from okul.models import SinifSube

    ogrenci = instance.ogrenci

    try:
        sinif_sube = SinifSube.objects.get(
            sinif=ogrenci.sinif,
            sube__iexact=ogrenci.sube,
        )
    except SinifSube.DoesNotExist:
        return

    SERVIS_ETIKET = {
        "rehberlik":      "REHBERLİK SERVİSİ",
        "disiplin":       "DİSİPLİN KURULU",
        "muduriyetcagri": "MÜDÜRİYET",
    }
    servis_adi = SERVIS_ETIKET.get(instance.servis, instance.servis.upper())

    baslik = f"📢 ÖĞRENCİ ÇAĞRISI — {servis_adi}"

    satir1 = f"{ogrenci.adi} {ogrenci.soyadi}"
    satir2_parcalar = []
    if instance.ders_saati:
        satir2_parcalar.append(f"{instance.ders_saati}. ders saatinde")
    satir2_parcalar.append(f"{servis_adi}'ne çağrılmıştır.")
    if instance.cagri_metni:
        satir2_parcalar.append(f"Not: {instance.cagri_metni}")

    mesaj = f"{satir1}\n{' '.join(satir2_parcalar)}"

    gonderen = instance.kayit_eden_kullanici
    sinif_bildirimi_gonder(
        sinif_sube, baslik, mesaj, BildirimLog.TUR_CAGRI, gonderen
    )


# ──────────────────────────────────────────────
# Duyuru sinyali
# ──────────────────────────────────────────────

@receiver(post_save, sender="duyuru.Duyuru")
def duyuru_bildirimi_gonder(sender, instance, created, **kwargs):
    if not created:
        return

    from bildirim_gonderici.services import sinif_bildirimi_gonder
    from bildirim_gonderici.models import BildirimLog

    baslik = f"📣 DUYURU — {instance.sinif}"
    mesaj = instance.mesaj
    if instance.ders_saati:
        mesaj = f"{instance.ders_saati}. Ders Saati\n{mesaj}"

    gonderen = instance.olusturan
    sinif_bildirimi_gonder(
        instance.sinif, baslik, mesaj, BildirimLog.TUR_DUYURU, gonderen
    )
