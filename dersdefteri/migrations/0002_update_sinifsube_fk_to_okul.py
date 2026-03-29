"""
SeparateDatabaseAndState: DersDefteri.sinif_sube FK referansını
nobet.SinifSube → okul.SinifSube olarak günceller.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dersdefteri", "0001_initial"),
        ("okul", "0005_add_sinifsube"),
        ("nobet", "0019_remove_sinifsube"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="dersdefteri",
                    name="sinif_sube",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ders_defterleri",
                        to="okul.sinifsube",
                        verbose_name="Sınıf / Şube",
                    ),
                ),
            ],
        ),
    ]
