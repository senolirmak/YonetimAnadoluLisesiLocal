from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0038_add_derssaatleri"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'sinav_derssaatleri' AND column_name = 'ders_no') THEN
                        ALTER TABLE sinav_derssaatleri RENAME COLUMN ders_no TO derssaati_no;
                        ALTER TABLE sinav_derssaatleri RENAME COLUMN ders_baslangic TO derssaati_baslangic;
                        ALTER TABLE sinav_derssaatleri RENAME COLUMN ders_bitis TO derssaati_bitis;
                    END IF;
                END $$;
            """,
            reverse_sql="""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'sinav_derssaatleri' AND column_name = 'derssaati_no') THEN
                        ALTER TABLE sinav_derssaatleri RENAME COLUMN derssaati_no TO ders_no;
                        ALTER TABLE sinav_derssaatleri RENAME COLUMN derssaati_baslangic TO ders_baslangic;
                        ALTER TABLE sinav_derssaatleri RENAME COLUMN derssaati_bitis TO ders_bitis;
                    END IF;
                END $$;
            """,
        ),
    ]
