"""
SeparateDatabaseAndState: SinifSube modelini nobet app state'inden kaldırır.
Tablo silinmez; okul app'i sahiplenmiştir.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nobet", "0018_remove_school_calendar_models"),
        ("okul", "0005_add_sinifsube"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel("SinifSube"),
            ],
        ),
    ]
