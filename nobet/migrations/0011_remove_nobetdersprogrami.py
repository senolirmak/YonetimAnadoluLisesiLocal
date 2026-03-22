"""
State-only migration: NobetDersProgrami modeli dersprogrami app'e taşındı.
Veritabanı tablosu (nobet_dersprogrami) değiştirilmiyor.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("nobet", "0010_nobetpersonel_user"),
        ("dersprogrami", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="NobetDersProgrami"),
            ],
            database_operations=[],
        ),
    ]
