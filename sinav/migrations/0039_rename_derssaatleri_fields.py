from django.db import migrations

# Bu migration, önceden dağıtılmış Postgres veritabanlarında (model state zaten
# doğru alan adlarını gösterdiği için düz RenameField yerine) ham SQL ile eski
# sütun adlarını yeni adlara taşır. DO $$ ... $$ bloğu Postgres'e özgüdür ve
# sqlite'ta (örn. test veritabanında) syntax error verir; bu yüzden yalnızca
# Postgres backend'inde çalıştırılır. Taze kurulumlarda (sqlite test DB dahil)
# sütunlar zaten güncel adlarıyla oluştuğundan burada yapılacak bir şey yoktur.


def _rename_ileri(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'sinav_derssaatleri' AND column_name = 'ders_no') THEN
                    ALTER TABLE sinav_derssaatleri RENAME COLUMN ders_no TO derssaati_no;
                    ALTER TABLE sinav_derssaatleri RENAME COLUMN ders_baslangic TO derssaati_baslangic;
                    ALTER TABLE sinav_derssaatleri RENAME COLUMN ders_bitis TO derssaati_bitis;
                END IF;
            END $$;
            """
        )


def _rename_geri(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'sinav_derssaatleri' AND column_name = 'derssaati_no') THEN
                    ALTER TABLE sinav_derssaatleri RENAME COLUMN derssaati_no TO ders_no;
                    ALTER TABLE sinav_derssaatleri RENAME COLUMN derssaati_baslangic TO ders_baslangic;
                    ALTER TABLE sinav_derssaatleri RENAME COLUMN derssaati_bitis TO ders_bitis;
                END IF;
            END $$;
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0038_add_derssaatleri"),
    ]

    operations = [
        migrations.RunPython(_rename_ileri, _rename_geri),
    ]
