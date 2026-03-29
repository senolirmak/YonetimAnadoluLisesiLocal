"""
SeparateDatabaseAndState: EgitimOgretimYili, OkulDonem, OkulBilgi modellerini
nobet app'inden okul app'ine taşır. Tablolar aynı isimde kaldığından
veritabanına hiçbir şey yazılmaz; sadece migration state güncellenir.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("okul", "0002_rename_mudur_yardimcisi_to_okul_yonetici"),
        ("nobet", "0017_okul_donem_egitim_yili_fk"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="EgitimOgretimYili",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("egitim_yili", models.CharField(help_text="Örnek: 2025-2026", max_length=9, unique=True, verbose_name="Eğitim-Öğretim Yılı")),
                        ("egitim_baslangic", models.DateField(verbose_name="Yıl Başlangıç Tarihi")),
                        ("egitim_bitis", models.DateField(verbose_name="Yıl Bitiş Tarihi")),
                    ],
                    options={
                        "verbose_name": "Eğitim-Öğretim Yılı",
                        "verbose_name_plural": "Eğitim-Öğretim Yılları",
                        "db_table": "egitim_ogretim_yili",
                        "ordering": ["-egitim_yili"],
                    },
                ),
                migrations.CreateModel(
                    name="OkulDonem",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("donem", models.PositiveSmallIntegerField(choices=[(1, "1. Dönem"), (2, "2. Dönem")], verbose_name="Dönem")),
                        ("baslangic", models.DateField(verbose_name="Başlangıç Tarihi")),
                        ("bitis", models.DateField(verbose_name="Bitiş Tarihi")),
                        ("egitim_yili", models.ForeignKey(
                            blank=True, null=True,
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name="donemleri",
                            to="okul.egitimogretimyili",
                            verbose_name="Eğitim-Öğretim Yılı",
                        )),
                    ],
                    options={
                        "verbose_name": "Okul Dönemi",
                        "verbose_name_plural": "Okul Dönemleri",
                        "db_table": "okul_donem",
                        "ordering": ["baslangic"],
                    },
                ),
                migrations.CreateModel(
                    name="OkulBilgi",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("okul_kodu", models.CharField(blank=True, max_length=20, verbose_name="Okul Kodu")),
                        ("okul_adi", models.CharField(blank=True, max_length=200, verbose_name="Okul Adı")),
                        ("okul_muduru", models.CharField(blank=True, max_length=100, verbose_name="Okul Müdürü")),
                        ("okul_donem", models.ForeignKey(
                            blank=True, null=True,
                            on_delete=django.db.models.deletion.SET_NULL,
                            related_name="+",
                            to="okul.okuldonem",
                            verbose_name="Aktif Dönem",
                        )),
                        ("okul_egtyil", models.ForeignKey(
                            blank=True, null=True,
                            on_delete=django.db.models.deletion.SET_NULL,
                            related_name="+",
                            to="okul.egitimogretimyili",
                            verbose_name="Aktif Eğitim-Öğretim Yılı",
                        )),
                    ],
                    options={
                        "verbose_name": "Okul Bilgisi",
                        "verbose_name_plural": "Okul Bilgileri",
                        "db_table": "okul_bilgi",
                    },
                ),
            ],
        ),
    ]
