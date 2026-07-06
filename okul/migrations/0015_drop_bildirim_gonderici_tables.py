"""
bildirim_gonderici app'i kaldırıldı (sınıf tahtası bildirim özelliği). Var olan
kurulumlarda kalan bildirim_gonderici tablolarını siler.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("okul", "0014_personel_durum_alter_personel_gorev_tipi"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS bildirim_gonderici_bildirimlog;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS bildirim_gonderici_siniftahta;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
