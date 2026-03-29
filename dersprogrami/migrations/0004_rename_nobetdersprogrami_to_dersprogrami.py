"""
RenameModel: NobetDersProgrami → DersProgrami.
db_table="nobet_dersprogrami" sabit tutulduğu için veritabanı tablosuna dokunulmaz.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("dersprogrami", "0003_update_nobetpersonel_fk_to_okul"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="NobetDersProgrami",
            new_name="DersProgrami",
        ),
    ]
