"""MuduriyCagri tablosu kaldırılıyor — veriler cagri app migration'ında taşınacak."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("muduriyetcagri", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel("MuduriyCagri"),
    ]
