"""
State-only migration: Devamsizlik modeli personeldevamsizlik app'e taşınıyor.
Veritabanı tablosu (nobet_devamsizlik) değiştirilmiyor.
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("nobet", "0011_remove_nobetdersprogrami"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Devamsizlik",
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
                        ("baslangic_tarihi", models.DateField()),
                        ("bitis_tarihi", models.DateField(null=True, blank=True)),
                        (
                            "devamsiz_tur",
                            models.IntegerField(
                                choices=[
                                    (0, "Kısmı Devamsız"),
                                    (1, "Raporlu"),
                                    (2, "Mazeret İzinli/İzinli"),
                                    (3, "Görevli İzinli"),
                                ],
                                default=0,
                            ),
                        ),
                        ("sure", models.IntegerField(default=1)),
                        ("aciklama", models.CharField(blank=True, max_length=200, null=True)),
                        (
                            "ders_saatleri",
                            models.CharField(
                                default="1,2,3,4,5,6,7,8",
                                help_text="Virgülle ayrılmış ders saatleri (Örn: 1,2,3)",
                                max_length=50,
                            ),
                        ),
                        (
                            "gorevlendirme_yapilsin",
                            models.BooleanField(
                                default=True,
                                help_text="Bu devamsızlık için boş derslere nöbetçi öğretmen ataması yapılsın mı?",
                            ),
                        ),
                        (
                            "ogretmen",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="devamsizlik",
                                to="nobet.nobetogretmen",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Devamsızlık Kaydı",
                        "verbose_name_plural": "Devamsızlık Kayıtları",
                        "db_table": "nobet_devamsizlik",
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
