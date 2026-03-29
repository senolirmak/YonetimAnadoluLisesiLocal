"""
SeparateDatabaseAndState: Faaliyet.ogretmen FK'sını nobet.NobetPersonel'den
okul.NobetPersonel'e günceller. Veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("faaliyet", "0003_onaylayan_bilgisi"),
        ("okul", "0009_rename_nobetpersonel_to_personel"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="faaliyet",
                    name="ogretmen",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="faaliyetler",
                        to="okul.personel",
                        verbose_name="Öğretmen",
                    ),
                ),
            ],
        ),
    ]
