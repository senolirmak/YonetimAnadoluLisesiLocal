"""
Adım 3/3: Eski ders_saati (IntegerField) kaldır,
ders_saati_fk → ders_saati olarak yeniden adlandır.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("devamsizlik", "0003_data_ders_saati_fk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="ogrencidevamsizlik",
            name="ders_saati",
        ),
        migrations.RenameField(
            model_name="ogrencidevamsizlik",
            old_name="ders_saati_fk",
            new_name="ders_saati",
        ),
    ]
