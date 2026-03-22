"""
State-only migration: NobetDersProgrami modeli dersprogrami app'e taşınıyor.
Veritabanı tablosu (nobet_dersprogrami) değiştirilmiyor.
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("nobet", "0010_nobetpersonel_user"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="NobetDersProgrami",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "gun",
                            models.CharField(
                                choices=[
                                    ("Monday", "Pazartesi"),
                                    ("Tuesday", "Salı"),
                                    ("Wednesday", "Çarşamba"),
                                    ("Thursday", "Perşembe"),
                                    ("Friday", "Cuma"),
                                    ("Saturday", "Cumartesi"),
                                    ("Sunday", "Pazar"),
                                ],
                                max_length=10,
                            ),
                        ),
                        ("giris_saat", models.TimeField()),
                        ("cikis_saat", models.TimeField()),
                        ("ders_adi", models.CharField(max_length=100)),
                        ("ders_saati", models.IntegerField()),
                        ("ders_saati_adi", models.CharField(max_length=10)),
                        ("uygulama_tarihi", models.DateField(default=django.utils.timezone.now)),
                        (
                            "ogretmen",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="dersprogrami",
                                to="nobet.nobetpersonel",
                            ),
                        ),
                        (
                            "sinif_sube",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="dersprogrami",
                                to="nobet.sinifsube",
                                verbose_name="Sınıf/Şube",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Ders Programı",
                        "verbose_name_plural": "Haftalık Ders Programı",
                        "db_table": "nobet_dersprogrami",
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
