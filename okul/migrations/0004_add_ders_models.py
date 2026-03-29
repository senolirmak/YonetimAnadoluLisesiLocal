"""
SeparateDatabaseAndState: DersHavuzu ve DersSaatleri modellerini
sinav app'inden okul app'ine taşır. Tablolar aynı isimde kaldığından
veritabanına hiçbir şey yazılmaz; sadece migration state güncellenir.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("okul", "0003_add_school_calendar_models"),
        ("sinav", "0042_update_sinavbilgisi_fk_to_okul"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="DersHavuzu",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("ders_adi", models.CharField(max_length=200, unique=True)),
                    ],
                    options={
                        "verbose_name": "Ders",
                        "verbose_name_plural": "Ders Havuzu",
                        "db_table": "sinav_dershavuzu",
                        "ordering": ["ders_adi"],
                    },
                ),
                migrations.CreateModel(
                    name="DersSaatleri",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("derssaati_no", models.PositiveIntegerField(unique=True, verbose_name="Ders No")),
                        ("derssaati_baslangic", models.TimeField(verbose_name="Ders Başlangıç")),
                        ("derssaati_bitis", models.TimeField(verbose_name="Ders Bitiş")),
                    ],
                    options={
                        "verbose_name": "Ders Saati",
                        "verbose_name_plural": "Ders Saatleri",
                        "db_table": "sinav_derssaatleri",
                        "ordering": ["derssaati_no"],
                    },
                ),
            ],
        ),
    ]
