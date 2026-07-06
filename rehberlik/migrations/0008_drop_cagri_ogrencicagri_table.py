"""
cagri app'i kaldırıldı; öğrenci çağrı özelliği rehberlik/disiplin/muduriyetcagri'den
tamamen çıkarıldı. Var olan kurulumlarda kalan cagri_ogrencicagri tablosunu siler.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("rehberlik", "0007_update_nobetpersonel_fk_to_okul"),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS cagri_ogrencicagri;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
