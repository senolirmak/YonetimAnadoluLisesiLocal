"""
RenameModel: NobetPersonel → Personel (okul app içinde).
db_table="nobet_personel" sabit tutulduğu için veritabanı tablosuna dokunulmaz.
FK referansları migration state'de otomatik cascade güncellenir.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("okul", "0008_alter_okuldonem_unique_together"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="NobetPersonel",
            new_name="Personel",
        ),
    ]
