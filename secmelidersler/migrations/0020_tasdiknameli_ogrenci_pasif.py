from django.db import migrations


def tasdiknameli_ogrencileri_pasife_al(apps, schema_editor):
    OgrenciTasdikname = apps.get_model("secmelidersler", "OgrenciTasdikname")
    Ogrenci = apps.get_model("ogrenci", "Ogrenci")
    tasdiknameli_ids = OgrenciTasdikname.objects.values_list("ogrenci_id", flat=True)
    Ogrenci.objects.filter(pk__in=tasdiknameli_ids, aktif=True).update(aktif=False)


def geri_al(apps, schema_editor):
    # Geri alma: hangi öğrencinin bu migration tarafından pasife alındığı ayırt
    # edilemediği için kasıtlı olarak no-op bırakılıyor.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("secmelidersler", "0019_secmelidershavuzu_branslar"),
        ("ogrenci", "0013_ogrenci_aktif"),
    ]

    operations = [
        migrations.RunPython(tasdiknameli_ogrencileri_pasife_al, geri_al),
    ]
