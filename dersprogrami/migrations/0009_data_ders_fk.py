"""
Adım 2/3: DersProgrami.ders_adi → DersHavuzu FK veri migrasyonu.
Her ders_adi için DersHavuzu kaydı get_or_create edilir.
"""

from django.db import migrations


def ders_adi_to_fk(apps, schema_editor):
    DersProgrami = apps.get_model("dersprogrami", "DersProgrami")
    DersHavuzu = apps.get_model("okul", "DersHavuzu")

    for dp in DersProgrami.objects.filter(ders_adi__isnull=False).exclude(ders_adi=""):
        obj, _ = DersHavuzu.objects.get_or_create(ders_adi=dp.ders_adi.strip())
        dp.ders_fk = obj
        dp.save(update_fields=["ders_fk"])


def fk_to_ders_adi(apps, schema_editor):
    DersProgrami = apps.get_model("dersprogrami", "DersProgrami")
    for dp in DersProgrami.objects.select_related("ders_fk").filter(ders_fk__isnull=False):
        dp.ders_adi = dp.ders_fk.ders_adi
        dp.save(update_fields=["ders_adi"])


class Migration(migrations.Migration):

    dependencies = [
        ("dersprogrami", "0008_add_ders_fk"),
    ]

    operations = [
        migrations.RunPython(ders_adi_to_fk, reverse_code=fk_to_ders_adi),
    ]
