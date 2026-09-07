from django.db import migrations


def gecmis_gecisleri_arsivle(apps, schema_editor):
    """Daha önce uygulanmış Sene Sonu Geçişlerine göre geriye dönük arşivleme yapar.

    Bkz. nobet/migrations/0031_gecmis_gecisleri_arsivle.py ve
    ogrencinobet/migrations/0003_gecmis_gecisleri_arsivle.py — aynı mantık.
    """
    SeneSonuGecisi = apps.get_model("senesonu", "SeneSonuGecisi")
    Devamsizlik = apps.get_model("personeldevamsizlik", "Devamsizlik")

    for gecis in (
        SeneSonuGecisi.objects.filter(uygulandi=True)
        .select_related("eski_egitim_yili")
        .order_by("uygulama_zamani")
    ):
        Devamsizlik.objects.filter(
            arsivlendi=False, baslangic_tarihi__lte=gecis.eski_egitim_yili.egitim_bitis
        ).update(arsivlendi=True)


def geri_al(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("personeldevamsizlik", "0002_devamsizlik_arsivlendi"),
        ("senesonu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(gecmis_gecisleri_arsivle, geri_al),
    ]
