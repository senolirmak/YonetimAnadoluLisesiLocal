from django.db import migrations


def populate_toplam_saat(apps, schema_editor):
    SinifSeviyeToplamSaat = apps.get_model("secmelidersler", "SinifSeviyeToplamSaat")
    for sinif_seviyesi in (9, 10, 11, 12):
        SinifSeviyeToplamSaat.objects.get_or_create(
            sinif_seviyesi=sinif_seviyesi,
            defaults={"haftalik_toplam_saat": 40},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("secmelidersler", "0009_sinif_seviye_toplam_saat"),
    ]

    operations = [
        migrations.RunPython(populate_toplam_saat, migrations.RunPython.noop),
    ]
