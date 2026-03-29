"""
Adım 2/3: Data migration — ders_saati int değerini DersSaatleri FK'sine dönüştür.
DersSaatleri.derssaati_no == DersProgrami.ders_saati eşleşmesiyle doldurur.
"""

from django.db import migrations


def doldur_ders_saati_fk(apps, schema_editor):
    DersProgrami = apps.get_model("dersprogrami", "DersProgrami")
    DersSaatleri = apps.get_model("okul", "DersSaatleri")

    ders_saati_map = {ds.derssaati_no: ds.pk for ds in DersSaatleri.objects.all()}

    for no, pk in ders_saati_map.items():
        DersProgrami.objects.filter(ders_saati=no).update(ders_saati_fk_id=pk)


def geri_al(apps, schema_editor):
    DersProgrami = apps.get_model("dersprogrami", "DersProgrami")
    DersProgrami.objects.update(ders_saati_fk=None)


class Migration(migrations.Migration):

    dependencies = [
        ("dersprogrami", "0005_add_ders_saati_fk"),
    ]

    operations = [
        migrations.RunPython(doldur_ders_saati_fk, geri_al),
    ]
