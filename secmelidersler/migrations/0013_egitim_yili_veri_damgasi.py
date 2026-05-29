"""
Veri migration: mevcut OrtakDers, SecmeliDersGrubu, Alan ve SinifSeviyeToplamSaat
kayıtlarına OkulBilgi'deki aktif eğitim-öğretim yılını (okul_egtyil) atar.

Aktif EÖY yoksa kayıtlar NULL olarak kalır — bir sonraki aktif yıl seçildiğinde
yeniden çalıştırılabilir (veya yönetim arayüzünden elle atanabilir).
"""

from django.db import migrations


def ata_egitim_yili(apps, schema_editor):
    OkulBilgi = apps.get_model("okul", "OkulBilgi")
    OrtakDers = apps.get_model("secmelidersler", "OrtakDers")
    SecmeliDersGrubu = apps.get_model("secmelidersler", "SecmeliDersGrubu")
    Alan = apps.get_model("secmelidersler", "Alan")
    SinifSeviyeToplamSaat = apps.get_model("secmelidersler", "SinifSeviyeToplamSaat")

    okul = OkulBilgi.objects.select_related("okul_egtyil").first()
    if not okul or not okul.okul_egtyil:
        return  # Aktif EÖY tanımlanmamış — kayıtlar NULL kalır

    yil = okul.okul_egtyil

    OrtakDers.objects.filter(egitim_yili__isnull=True).update(egitim_yili=yil)
    SecmeliDersGrubu.objects.filter(egitim_yili__isnull=True).update(egitim_yili=yil)
    Alan.objects.filter(egitim_yili__isnull=True).update(egitim_yili=yil)
    SinifSeviyeToplamSaat.objects.filter(egitim_yili__isnull=True).update(egitim_yili=yil)


class Migration(migrations.Migration):

    dependencies = [
        ("secmelidersler", "0012_egitim_yili_damgasi"),
        ("okul", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(ata_egitim_yili, migrations.RunPython.noop),
    ]
