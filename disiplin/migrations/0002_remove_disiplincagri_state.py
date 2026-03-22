"""
DisiplinCagri model sınıfı cagri app'ine taşındı.
DB tablosu (disiplin_cagri) korunuyor — veri migration cagri app'inde.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("disiplin", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel("DisiplinCagri"),
            ],
            database_operations=[],  # tabloyu silme
        ),
    ]
