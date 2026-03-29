"""
SeparateDatabaseAndState: NobetDersProgrami.ogretmen FK'sını nobet.NobetPersonel'den
okul.NobetPersonel'e günceller. Veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dersprogrami", "0002_update_sinifsube_fk_to_okul"),
        ("okul", "0006_add_nobetpersonel"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="nobetdersprogrami",
                    name="ogretmen",
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dersprogrami",
                        to="okul.nobetpersonel",
                    ),
                ),
            ],
        ),
    ]
