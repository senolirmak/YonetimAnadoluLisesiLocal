"""
OgrenciDevamsizlik modeli devamsizlik app'ine taşındı.
SeparateDatabaseAndState ile Django state'inden kaldırıyoruz,
veritabanı tablosuna dokunmuyoruz (devamsizlik app'i sahiplenecek).
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("ogrenci", "0003_ogrencidevamsizlik"),
        ("devamsizlik", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="OgrenciDevamsizlik"),
            ],
            database_operations=[],  # Tabloyu silme
        ),
    ]
