"""
SeparateDatabaseAndState: SinifSube modelini nobet app'inden okul app'ine taşır.
Tablo adı nobet_sinifsube olarak korunur; veritabanına dokunulmaz.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("okul", "0004_add_ders_models"),
        ("nobet", "0018_remove_school_calendar_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="SinifSube",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("sinif", models.IntegerField()),
                        ("sube", models.CharField(max_length=2)),
                    ],
                    options={
                        "verbose_name": "Sınıf Şube",
                        "verbose_name_plural": "Sınıf ve Şubeler",
                        "db_table": "nobet_sinifsube",
                    },
                ),
                migrations.AlterUniqueTogether(
                    name="sinifsube",
                    unique_together={("sinif", "sube")},
                ),
            ],
        ),
    ]
