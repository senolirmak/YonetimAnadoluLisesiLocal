"""
Veri migration: mevcut NobetGorevi, GunlukNobetCizelgesi ve MazeretSalonGorevi
kayıtlarına OkulBilgi'deki aktif eğitim-öğretim yılını (okul_egtyil) ve dönemi
(okul_donem) atar.

Aktif EÖY/dönem yoksa kayıtlar NULL olarak kalır — bir sonraki aktif yıl/dönem
seçildiğinde yeniden çalıştırılabilir (veya yönetim arayüzünden elle atanabilir).
"""

from django.db import migrations


def ata_egitim_yili_donem(apps, schema_editor):
    OkulBilgi = apps.get_model("okul", "OkulBilgi")
    NobetGorevi = apps.get_model("nobet", "NobetGorevi")
    GunlukNobetCizelgesi = apps.get_model("nobet", "GunlukNobetCizelgesi")
    MazeretSalonGorevi = apps.get_model("nobet", "MazeretSalonGorevi")

    okul = OkulBilgi.objects.select_related("okul_egtyil", "okul_donem").first()
    if not okul:
        return

    modeller = [NobetGorevi, GunlukNobetCizelgesi, MazeretSalonGorevi]
    if okul.okul_egtyil:
        for model in modeller:
            model.objects.filter(egitim_yili__isnull=True).update(egitim_yili=okul.okul_egtyil)
    if okul.okul_donem:
        for model in modeller:
            model.objects.filter(donem__isnull=True).update(donem=okul.okul_donem)


class Migration(migrations.Migration):

    dependencies = [
        ("nobet", "0027_gunluknobetcizelgesi_donem_and_more"),
    ]

    operations = [
        migrations.RunPython(ata_egitim_yili_donem, migrations.RunPython.noop),
    ]
