"""
Adım 3/3: Eski CharField nobet_yeri'ni sil, FK alanını nobet_yeri olarak yeniden adlandır.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nobet", "0024_data_nobetgorevi_nobet_yeri_fk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="nobetgorevi",
            name="nobet_yeri",
        ),
        migrations.RenameField(
            model_name="nobetgorevi",
            old_name="nobet_yeri_fk",
            new_name="nobet_yeri",
        ),
    ]
