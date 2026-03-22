"""
Tablo zaten 'ogrenci' migration'ı tarafından oluşturulmuş.
SeparateDatabaseAndState ile Django'ya model state'i tanıtıyoruz,
veritabanında hiçbir şey yapmıyoruz.
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ogrenci", "0003_ogrencidevamsizlik"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="OgrenciDevamsizlik",
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
                            "tarih",
                            models.DateField(
                                default=django.utils.timezone.localdate, verbose_name="Tarih"
                            ),
                        ),
                        ("ders_saati", models.IntegerField(verbose_name="Ders Saati")),
                        ("ders_adi", models.CharField(max_length=100, verbose_name="Ders Adı")),
                        ("ogretmen_adi", models.CharField(max_length=100, verbose_name="Öğretmen")),
                        (
                            "aciklama",
                            models.CharField(
                                blank=True, max_length=200, null=True, verbose_name="Açıklama"
                            ),
                        ),
                        ("olusturma_zamani", models.DateTimeField(auto_now_add=True)),
                        (
                            "ogrenci",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="devamsizliklar",
                                to="ogrenci.ogrenci",
                                verbose_name="Öğrenci",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Öğrenci Devamsızlık",
                        "verbose_name_plural": "Öğrenci Devamsızlıkları",
                        "db_table": "ogrenci_devamsizlik",
                        "ordering": ["-tarih", "ders_saati"],
                        "unique_together": {("ogrenci", "tarih", "ders_saati")},
                    },
                ),
            ],
            database_operations=[],  # Tablo zaten var, DB'ye dokunma
        ),
    ]
