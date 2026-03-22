"""
Veri cagri app'ine taşındıktan sonra rehberlik_ogrenci_cagri tablosunu siler.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("rehberlik", "0005_remove_ogrencicagri_state"),
        ("cagri", "0002_migrate_data"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS rehberlik_ogrenci_cagri;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
