from django.db import migrations


def gecmis_gecisleri_arsivle(apps, schema_editor):
    """Daha önce uygulanmış Sene Sonu Geçişlerine göre geriye dönük arşivleme yapar.

    Bkz. ogrencinobet/migrations/0003_gecmis_gecisleri_arsivle.py — aynı mantık.
    """
    SeneSonuGecisi = apps.get_model("senesonu", "SeneSonuGecisi")
    Faaliyet = apps.get_model("faaliyet", "Faaliyet")

    for gecis in (
        SeneSonuGecisi.objects.filter(uygulandi=True)
        .select_related("eski_egitim_yili")
        .order_by("uygulama_zamani")
    ):
        Faaliyet.objects.filter(
            arsivlendi=False, tarih__lte=gecis.eski_egitim_yili.egitim_bitis
        ).update(arsivlendi=True)


def geri_al(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("faaliyet", "0005_faaliyet_arsivlendi"),
        ("senesonu", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(gecmis_gecisleri_arsivle, geri_al),
    ]
