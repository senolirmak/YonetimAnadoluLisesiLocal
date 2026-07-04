"""
Veri migration: mevcut OgrenciMuaf ve SinifOturmaDuzeni kayıtlarına
OkulBilgi'deki aktif eğitim-öğretim yılını (okul_egtyil) atar.

Aktif EÖY yoksa kayıtlar NULL olarak kalır — bir sonraki aktif yıl seçildiğinde
yeniden çalıştırılabilir (veya yönetim arayüzünden elle atanabilir).
"""

from django.db import migrations


def ata_egitim_yili(apps, schema_editor):
    OkulBilgi = apps.get_model("okul", "OkulBilgi")
    OgrenciMuaf = apps.get_model("ogrenci", "OgrenciMuaf")
    SinifOturmaDuzeni = apps.get_model("ogrenci", "SinifOturmaDuzeni")

    okul = OkulBilgi.objects.select_related("okul_egtyil").first()
    if not okul or not okul.okul_egtyil:
        return  # Aktif EÖY tanımlanmamış — kayıtlar NULL kalır

    yil = okul.okul_egtyil

    OgrenciMuaf.objects.filter(egitim_yili__isnull=True).update(egitim_yili=yil)
    SinifOturmaDuzeni.objects.filter(egitim_yili__isnull=True).update(egitim_yili=yil)


class Migration(migrations.Migration):

    dependencies = [
        ("ogrenci", "0011_alter_ogrencimuaf_unique_together_and_more"),
        ("okul", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(ata_egitim_yili, migrations.RunPython.noop),
    ]
