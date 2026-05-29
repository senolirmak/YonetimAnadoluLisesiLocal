"""
Veri migration: "REHBERLİK VE YÖNLENDİRME" dersini
  - OrtakDersHavuzu'na (1 saat, aktif)
  - OrtakDers'e 9, 10, 11, 12. sınıfların tümüne (1 saat, sıra en sona)
ekler. get_or_create kullandığından tekrar çalıştırılması güvenlidir.
"""

from django.db import migrations
from django.db.models import Max

DERS_ADI = "REHBERLİK VE YÖNLENDİRME"


def ekle(apps, schema_editor):
    OrtakDersHavuzu = apps.get_model("secmelidersler", "OrtakDersHavuzu")
    OrtakDers = apps.get_model("secmelidersler", "OrtakDers")

    # 1) Ortak Ders Havuzu
    maks_sira = OrtakDersHavuzu.objects.aggregate(m=Max("sira"))["m"] or 0
    OrtakDersHavuzu.objects.get_or_create(
        ders_adi=DERS_ADI,
        defaults={
            "derssaati": "1",
            "sira": maks_sira + 1,
            "aktif": True,
        },
    )

    # 2) OrtakDers — her sınıf seviyesi için
    for sinif_seviyesi in (9, 10, 11, 12):
        maks_sira = (
            OrtakDers.objects
            .filter(sinif_seviyesi=sinif_seviyesi)
            .aggregate(m=Max("sira"))["m"] or 0
        )
        OrtakDers.objects.get_or_create(
            sinif_seviyesi=sinif_seviyesi,
            ders_adi=DERS_ADI,
            defaults={
                "haftalik_saat": 1,
                "sira": maks_sira + 1,
            },
        )


def geri_al(apps, schema_editor):
    OrtakDersHavuzu = apps.get_model("secmelidersler", "OrtakDersHavuzu")
    OrtakDers = apps.get_model("secmelidersler", "OrtakDers")
    OrtakDersHavuzu.objects.filter(ders_adi=DERS_ADI).delete()
    OrtakDers.objects.filter(ders_adi=DERS_ADI).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("secmelidersler", "0010_sinif_seviye_toplam_saat_veri"),
    ]

    operations = [
        migrations.RunPython(ekle, geri_al),
    ]
