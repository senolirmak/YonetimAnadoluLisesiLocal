"""
Veri cagri app'ine taşındıktan sonra disiplin_cagri tablosunu siler.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("disiplin", "0002_remove_disiplincagri_state"),
        ("cagri", "0002_migrate_data"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS disiplin_cagri;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
