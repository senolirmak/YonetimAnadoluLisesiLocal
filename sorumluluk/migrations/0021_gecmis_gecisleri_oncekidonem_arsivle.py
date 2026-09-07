from django.db import migrations


def gecmis_gecisleri_arsivle(apps, schema_editor):
    """Daha önce uygulanmış Sene Sonu Geçişlerine göre, eski eğitim-öğretim yılına
    ait OncekiDonem kayıtlarını geriye dönük arşivler.

    Bkz. senesonu/services.py: gecis_uygula ve
    sorumluluk/migrations/0019_gecmis_gecisleri_arsivle.py — aynı mantık.
    """
    SeneSonuGecisi = apps.get_model("senesonu", "SeneSonuGecisi")
    OncekiDonem = apps.get_model("sorumluluk", "OncekiDonem")

    for gecis in (
        SeneSonuGecisi.objects.filter(uygulandi=True)
        .select_related("eski_egitim_yili")
        .order_by("uygulama_zamani")
    ):
        OncekiDonem.objects.filter(
            arsivlendi=False, egitim_yili=gecis.eski_egitim_yili_id
        ).update(arsivlendi=True)


def geri_al(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("sorumluluk", "0020_oncekidonem_arsivlendi"),
        ("senesonu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(gecmis_gecisleri_arsivle, geri_al),
    ]
