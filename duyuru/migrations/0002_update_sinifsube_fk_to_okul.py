"""
SeparateDatabaseAndState: Duyuru.sinif FK referansını
nobet.SinifSube → okul.SinifSube olarak günceller.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("duyuru", "0001_initial"),
        ("okul", "0005_add_sinifsube"),
        ("nobet", "0019_remove_sinifsube"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="duyuru",
                    name="sinif",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="duyurular",
                        to="okul.sinifsube",
                        verbose_name="Sınıf/Şube",
                    ),
                ),
            ],
        ),
    ]
