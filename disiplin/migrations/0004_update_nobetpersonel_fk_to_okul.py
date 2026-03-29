"""
SeparateDatabaseAndState: DisiplinGorusme.kayit_eden FK'sını nobet.NobetPersonel'den
okul.NobetPersonel'e günceller. Veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("disiplin", "0003_drop_disiplincagri_table"),
        ("okul", "0006_add_nobetpersonel"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="disiplingorusme",
                    name="kayit_eden",
                    field=models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="disiplin_gorusmeleri",
                        to="okul.nobetpersonel",
                        verbose_name="Kaydeden",
                    ),
                ),
            ],
        ),
    ]
