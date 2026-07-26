"""
Veri migration: mevcut DersProgrami kayıtlarına OkulBilgi'deki aktif eğitim-öğretim
yılını (okul_egtyil) ve dönemi (okul_donem) atar.

Aktif EÖY/dönem yoksa kayıtlar NULL olarak kalır — bir sonraki aktif yıl/dönem
seçildiğinde yeniden çalıştırılabilir (veya yönetim arayüzünden elle atanabilir).
"""

from django.db import migrations


def ata_egitim_yili_donem(apps, schema_editor):
    OkulBilgi = apps.get_model("okul", "OkulBilgi")
    DersProgrami = apps.get_model("dersprogrami", "DersProgrami")

    okul = OkulBilgi.objects.select_related("okul_egtyil", "okul_donem").first()
    if not okul:
        return

    if okul.okul_egtyil:
        DersProgrami.objects.filter(egitim_yili__isnull=True).update(egitim_yili=okul.okul_egtyil)
    if okul.okul_donem:
        DersProgrami.objects.filter(donem__isnull=True).update(donem=okul.okul_donem)


class Migration(migrations.Migration):

    dependencies = [
        ("dersprogrami", "0011_dersprogrami_donem_dersprogrami_egitim_yili"),
    ]

    operations = [
        migrations.RunPython(ata_egitim_yili_donem, migrations.RunPython.noop),
    ]
