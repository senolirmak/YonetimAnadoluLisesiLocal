"""
SeparateDatabaseAndState: NobetDersProgrami.sinif_sube FK referansını
nobet.SinifSube → okul.SinifSube olarak günceller.
Tablo aynı kaldığından veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dersprogrami", "0001_initial"),
        ("okul", "0005_add_sinifsube"),
        ("nobet", "0019_remove_sinifsube"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="nobetdersprogrami",
                    name="sinif_sube",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dersprogrami",
                        to="okul.sinifsube",
                        verbose_name="Sınıf/Şube",
                    ),
                ),
            ],
        ),
    ]
