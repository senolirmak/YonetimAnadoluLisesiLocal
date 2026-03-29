"""
SeparateDatabaseAndState: DersHavuzu ve DersSaatleri modellerini
sinav app state'inden kaldırır. Tablolar silinmez; okul app'i sahiplenmiştir.
FK referansları 0043'te zaten okul.*'a güncellendi.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0043_update_ders_fk_to_okul"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel("DersHavuzu"),
                migrations.DeleteModel("DersSaatleri"),
            ],
        ),
    ]
