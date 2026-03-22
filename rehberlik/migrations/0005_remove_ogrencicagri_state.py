"""
OgrenciCagri model sınıfı cagri app'ine taşındı.
DB tablosu (rehberlik_ogrenci_cagri) korunuyor — veri migration cagri app'inde.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("rehberlik", "0004_ogrencicagri_gorusme"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel("OgrenciCagri"),
            ],
            database_operations=[],  # tabloyu silme
        ),
    ]
