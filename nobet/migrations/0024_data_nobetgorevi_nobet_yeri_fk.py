"""
Adım 2/3: Data migration — mevcut nobet_yeri string değerlerini
NobetYerleri tablosuna ekle ve nobet_yeri_fk'yi doldur.
"""

from django.db import migrations


def doldur_nobet_yeri_fk(apps, schema_editor):
    NobetGorevi = apps.get_model("nobet", "NobetGorevi")
    NobetYerleri = apps.get_model("nobet", "NobetYerleri")

    # Tekil yer adlarını tek sorguda al
    yer_adlari = (
        NobetGorevi.objects.exclude(nobet_yeri="")
        .values_list("nobet_yeri", flat=True)
        .distinct()
    )

    # NobetYerleri kayıtlarını garanti et ve map'i hazırla
    yer_map = {}
    for ad in yer_adlari:
        if ad:
            obj, _ = NobetYerleri.objects.get_or_create(ad=ad)
            yer_map[ad] = obj.pk

    # Batch update: her yer adı için tek UPDATE sorgusu
    for ad, pk in yer_map.items():
        NobetGorevi.objects.filter(nobet_yeri=ad).update(nobet_yeri_fk_id=pk)


def geri_al(apps, schema_editor):
    NobetGorevi = apps.get_model("nobet", "NobetGorevi")
    NobetGorevi.objects.update(nobet_yeri_fk=None)


class Migration(migrations.Migration):

    dependencies = [
        ("nobet", "0023_nobetgorevi_add_nobet_yeri_fk"),
    ]

    operations = [
        migrations.RunPython(doldur_nobet_yeri_fk, geri_al),
    ]
