from django.db import migrations
from django.utils import timezone


def gecmis_gecisleri_arsivle(apps, schema_editor):
    """Daha önce uygulanmış Sene Sonu Geçişlerine göre, eski eğitim-öğretim yılına
    ait ve henüz arşivlenmemiş SorumluSinav kayıtlarını geriye dönük arşivler.

    Bkz. senesonu/services.py: gecis_uygula — aynı mantık. `arsivlendi` alanı bu
    projede zaten mevcuttu (manuel "Arşivle" aksiyonu), bu migration yalnızca daha
    önce elle arşivlenmemiş kalmış olabilecek eski yıl kayıtlarını tamamlar.
    """
    SeneSonuGecisi = apps.get_model("senesonu", "SeneSonuGecisi")
    SorumluSinav = apps.get_model("sorumluluk", "SorumluSinav")

    for gecis in (
        SeneSonuGecisi.objects.filter(uygulandi=True)
        .select_related("eski_egitim_yili")
        .order_by("uygulama_zamani")
    ):
        SorumluSinav.objects.filter(
            arsivlendi=False, egitim_yili=gecis.eski_egitim_yili_id
        ).update(arsivlendi=True, arsivlenme_tarihi=timezone.now())


def geri_al(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("sorumluluk", "0018_sorumluluk_salon_ilk_veri"),
        ("senesonu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(gecmis_gecisleri_arsivle, geri_al),
    ]
