"""
Adım 3/3: Eski ders_saati (IntegerField) kaldır,
ders_saati_fk → ders_saati olarak yeniden adlandır.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("devamsizlik", "0003_data_ders_saati_fk"),
    ]

    operations = [
        # unique_together "ders_saati" alanını kapsadığı için, SQLite bu alanı
        # kaldırıp aynı adla yeniden oluştururken (tablo yeniden kurularak
        # uygulanan ALTER TABLE emülasyonu) otomatik unique index'i eski sütunla
        # karıştırıp hata verebiliyor (Postgres'te sorun yok, gerçek ALTER TABLE
        # RENAME COLUMN kullanılıyor). Kısıtı alan değişikliklerinden önce
        # geçici olarak kaldırıp sonrasında aynı adla geri ekliyoruz — nihai
        # model state (ve zaten uygulanmış Postgres veritabanları) değişmiyor.
        migrations.AlterUniqueTogether(
            name="ogrencidevamsizlik",
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name="ogrencidevamsizlik",
            name="ders_saati",
        ),
        migrations.RenameField(
            model_name="ogrencidevamsizlik",
            old_name="ders_saati_fk",
            new_name="ders_saati",
        ),
        migrations.AlterUniqueTogether(
            name="ogrencidevamsizlik",
            unique_together={("ogrenci", "tarih", "ders_saati")},
        ),
    ]
