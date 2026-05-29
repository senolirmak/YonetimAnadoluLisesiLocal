from django.db import migrations


class Migration(migrations.Migration):
    """
    OgrenciSecim modeli ogrencidersleri app'ine taşındı.
    Tablo bırakılıyor — ogrencidersleri OgrenciSecmeliDers aynı tabloyu kullanır.
    """

    dependencies = [
        ("secmelidersler", "0007_ortak_havuz_derssaati"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="OgrenciSecim"),
            ],
            database_operations=[],  # Tabloyu silme — ogrencidersleri kullanıyor
        ),
    ]
