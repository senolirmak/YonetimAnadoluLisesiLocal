"""
Adım 2/3: OgrenciDevamsizlik.ders_saati (int) → DersSaatleri FK veri migrasyonu.
ders_saati=0 kayıtları (nöbet özel sabiti) ders_saati_fk=None olarak kalır.
"""

from django.db import migrations


def int_to_fk(apps, schema_editor):
    OgrenciDevamsizlik = apps.get_model("devamsizlik", "OgrenciDevamsizlik")
    DersSaatleri = apps.get_model("okul", "DersSaatleri")

    ders_saati_map = {ds.derssaati_no: ds for ds in DersSaatleri.objects.all()}
    for dd in OgrenciDevamsizlik.objects.filter(ders_saati_fk__isnull=True, ders_saati__gt=0):
        ds_obj = ders_saati_map.get(dd.ders_saati)
        if ds_obj:
            dd.ders_saati_fk = ds_obj
            dd.save(update_fields=["ders_saati_fk"])


def fk_to_int(apps, schema_editor):
    OgrenciDevamsizlik = apps.get_model("devamsizlik", "OgrenciDevamsizlik")
    for dd in OgrenciDevamsizlik.objects.select_related("ders_saati_fk").filter(
        ders_saati_fk__isnull=False
    ):
        dd.ders_saati = dd.ders_saati_fk.derssaati_no
        dd.save(update_fields=["ders_saati"])


class Migration(migrations.Migration):

    dependencies = [
        ("devamsizlik", "0002_add_ders_saati_fk"),
    ]

    operations = [
        migrations.RunPython(int_to_fk, reverse_code=fk_to_int),
    ]
