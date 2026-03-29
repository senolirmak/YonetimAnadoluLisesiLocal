"""
SeparateDatabaseAndState: NobetPersonel modelini nobet app state'inden kaldırır.
Tablo silinmez; okul app'i sahiplenmiştir.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nobet", "0020_update_nobetogretmen_fk"),
        ("okul", "0007_update_okulYonetici_personel_fk"),
        ("faaliyet", "0004_update_nobetpersonel_fk_to_okul"),
        ("rehberlik", "0007_update_nobetpersonel_fk_to_okul"),
        ("disiplin", "0004_update_nobetpersonel_fk_to_okul"),
        ("cagri", "0004_update_nobetpersonel_fk_to_okul"),
        ("dersprogrami", "0003_update_nobetpersonel_fk_to_okul"),
        ("dersdefteri", "0003_update_nobetpersonel_fk_to_okul"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel("NobetPersonel"),
            ],
        ),
    ]
