from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0012_sinavbilgisi_kurum"),
    ]

    operations = [
        migrations.CreateModel(
            name="DisVeri",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dosya_etiketi", models.CharField(
                    choices=[("ogrenci", "Öğrenci Listesi"), ("haftalik_program", "Haftalık Ders Programı")],
                    max_length=20,
                    verbose_name="Dosya Etiketi",
                )),
                ("yukleme_tarihi", models.DateTimeField(auto_now_add=True, verbose_name="Yükleme Tarihi")),
                ("gecerlilik_tarihi", models.DateField(verbose_name="Geçerlilik Tarihi")),
            ],
            options={
                "verbose_name": "Dış Veri",
                "verbose_name_plural": "Dış Veriler",
                "ordering": ["-yukleme_tarihi"],
            },
        ),
    ]
