"""
State-only migration: Devamsizlik modeli personeldevamsizlik app'e taşındı.
Veritabanı tablosu (nobet_devamsizlik) değiştirilmiyor.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("nobet", "0011_remove_nobetdersprogrami"),
        ("personeldevamsizlik", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="Devamsizlik"),
            ],
            database_operations=[],
        ),
    ]
