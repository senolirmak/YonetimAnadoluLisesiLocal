"""
Adım 2/3: DersDefteri.ders_saati (int) → DersSaatleri FK veri migrasyonu.
"""

from django.db import migrations


def int_to_fk(apps, schema_editor):
    DersDefteri = apps.get_model("dersdefteri", "DersDefteri")
    DersSaatleri = apps.get_model("okul", "DersSaatleri")

    ders_saati_map = {ds.derssaati_no: ds for ds in DersSaatleri.objects.all()}
    for dd in DersDefteri.objects.filter(ders_saati_fk__isnull=True):
        ds_obj = ders_saati_map.get(dd.ders_saati)
        if ds_obj:
            dd.ders_saati_fk = ds_obj
            dd.save(update_fields=["ders_saati_fk"])


def fk_to_int(apps, schema_editor):
    DersDefteri = apps.get_model("dersdefteri", "DersDefteri")
    for dd in DersDefteri.objects.select_related("ders_saati_fk").filter(ders_saati_fk__isnull=False):
        dd.ders_saati = dd.ders_saati_fk.derssaati_no
        dd.giris_saat = dd.ders_saati_fk.derssaati_baslangic
        dd.cikis_saat = dd.ders_saati_fk.derssaati_bitis
        dd.save(update_fields=["ders_saati", "giris_saat", "cikis_saat"])


class Migration(migrations.Migration):

    dependencies = [
        ("dersdefteri", "0004_add_ders_saati_fk"),
    ]

    operations = [
        migrations.RunPython(int_to_fk, reverse_code=fk_to_int),
    ]
