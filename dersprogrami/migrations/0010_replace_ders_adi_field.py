"""
Adım 3/3: Eski ders_adi CharField kaldır, ders_fk → ders olarak yeniden adlandır.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("dersprogrami", "0009_data_ders_fk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="dersprogrami",
            name="ders_adi",
        ),
        migrations.RenameField(
            model_name="dersprogrami",
            old_name="ders_fk",
            new_name="ders",
        ),
    ]
