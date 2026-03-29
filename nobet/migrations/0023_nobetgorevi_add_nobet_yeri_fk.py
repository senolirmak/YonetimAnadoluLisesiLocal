"""
Adım 1/3: NobetGorevi'ne nullable FK kolonu ekle.
Mevcut nobet_yeri CharField'a dokunulmaz.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nobet", "0022_add_nobetyerleri"),
    ]

    operations = [
        migrations.AddField(
            model_name="nobetgorevi",
            name="nobet_yeri_fk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="gorevler",
                to="nobet.nobetyerleri",
                verbose_name="Nöbet Yeri",
            ),
        ),
    ]
