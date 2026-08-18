"""
Adım 3/3: Eski ders_saati (int), giris_saat, cikis_saat alanlarını kaldır;
ders_saati_fk → ders_saati olarak yeniden adlandır.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("dersdefteri", "0005_data_ders_saati_fk"),
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
            name="dersdefteri",
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name="dersdefteri",
            name="ders_saati",
        ),
        migrations.RemoveField(
            model_name="dersdefteri",
            name="giris_saat",
        ),
        migrations.RemoveField(
            model_name="dersdefteri",
            name="cikis_saat",
        ),
        migrations.RenameField(
            model_name="dersdefteri",
            old_name="ders_saati_fk",
            new_name="ders_saati",
        ),
        migrations.AlterUniqueTogether(
            name="dersdefteri",
            unique_together={("ogretmen", "tarih", "sinif_sube", "ders_saati")},
        ),
    ]
