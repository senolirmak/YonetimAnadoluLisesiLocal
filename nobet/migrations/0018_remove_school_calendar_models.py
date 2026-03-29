"""
SeparateDatabaseAndState: EgitimOgretimYili, OkulDonem, OkulBilgi modellerini
nobet app state'inden kaldırır. Tablolar silinmez; okul app'i sahiplenmiştir.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nobet", "0017_okul_donem_egitim_yili_fk"),
        ("okul", "0003_add_school_calendar_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                # FK bağımlılıkları nedeniyle ters sırada siliyoruz
                migrations.DeleteModel("OkulBilgi"),
                migrations.DeleteModel("OkulDonem"),
                migrations.DeleteModel("EgitimOgretimYili"),
            ],
        ),
    ]
