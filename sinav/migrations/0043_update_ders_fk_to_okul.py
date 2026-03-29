"""
SeparateDatabaseAndState: SubeDers.ders, Takvim.ders, Takvim.ders_saati
FK referanslarını sinav.* → okul.* olarak günceller.
Tablolar aynı kaldığından veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0042_update_sinavbilgisi_fk_to_okul"),
        ("okul", "0004_add_ders_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="subeders",
                    name="ders",
                    field=models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sube_dersler",
                        to="okul.dershavuzu",
                    ),
                ),
                migrations.AlterField(
                    model_name="takvim",
                    name="ders",
                    field=models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="takvimler",
                        to="okul.dershavuzu",
                    ),
                ),
                migrations.AlterField(
                    model_name="takvim",
                    name="ders_saati",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="takvimler",
                        to="okul.derssaatleri",
                        verbose_name="Ders Saati",
                    ),
                ),
            ],
        ),
    ]
