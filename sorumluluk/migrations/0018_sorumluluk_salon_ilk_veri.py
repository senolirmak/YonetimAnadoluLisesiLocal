# -*- coding: utf-8 -*-
"""Var olan sabit salon listesini (Sorumluluk1/2/3 → Mazeret 1/2/3) SorumlulukSalon
tablosuna aktarır — bu geçişten önce üretilmiş SorumluGozetmen/SorumluOturmaPlani
kayıtlarındaki "SorumlulukN" değerleri, aynı sira/kod eşlemesiyle okunabilir adını
(salon_choices() üzerinden) korumaya devam etsin diye gereklidir."""
from django.db import migrations

VARSAYILAN_SALONLAR = [
    (1, "Mazeret 1"),
    (2, "Mazeret 2"),
    (3, "Mazeret 3"),
]


def ekle(apps, schema_editor):
    SorumlulukSalon = apps.get_model("sorumluluk", "SorumlulukSalon")
    if SorumlulukSalon.objects.exists():
        return
    SorumlulukSalon.objects.bulk_create([
        SorumlulukSalon(sira=sira, ad=ad, aktif=True) for sira, ad in VARSAYILAN_SALONLAR
    ])


def geri_al(apps, schema_editor):
    SorumlulukSalon = apps.get_model("sorumluluk", "SorumlulukSalon")
    SorumlulukSalon.objects.filter(
        sira__in=[sira for sira, _ in VARSAYILAN_SALONLAR],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('sorumluluk', '0017_sorumluluksalon_alter_sorumlugozetmen_salon_and_more'),
    ]

    operations = [
        migrations.RunPython(ekle, geri_al),
    ]
