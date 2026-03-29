"""
SeparateDatabaseAndState: NobetOgretmen.personel FK'sını nobet.NobetPersonel'den
okul.NobetPersonel'e günceller. Veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nobet", "0019_remove_sinifsube"),
        ("okul", "0009_rename_nobetpersonel_to_personel"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="nobetogretmen",
                    name="personel",
                    field=models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ogretmen",
                        to="okul.personel",
                    ),
                ),
            ],
        ),
    ]
