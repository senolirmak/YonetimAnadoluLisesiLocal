"""
SeparateDatabaseAndState: SubeDers.sube FK referansını
nobet.SinifSube → okul.SinifSube olarak günceller.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0044_remove_ders_models_from_sinav"),
        ("okul", "0005_add_sinifsube"),
        ("nobet", "0019_remove_sinifsube"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="subeders",
                    name="sube",
                    field=models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sinav_sube_dersler",
                        to="okul.sinifsube",
                    ),
                ),
            ],
        ),
    ]
