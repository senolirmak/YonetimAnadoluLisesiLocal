"""
Sorumluluk app model sadeleştirmesi:
  - SorumluGun + SorumluOturum + SorumluOturumDers (3 model hiyerarşi) kaldırıldı
  - SorumluTakvim (düz, ortaksinav Takvim modeliyle aynı mantık) eklendi
  - SorumluSinavParametre (ortaksinav CONFIG yapısına paralel parametre modeli) eklendi
  - SorumluOturmaPlani: oturum FK yerine tarih/oturum_no/saat alanları kullanıyor
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sorumluluk", "0001_initial"),
    ]

    operations = [
        # 1. Yeni SorumluTakvim tablosu
        migrations.CreateModel(
            name="SorumluTakvim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tarih",          models.DateField(verbose_name="Tarih")),
                ("oturum_no",      models.PositiveSmallIntegerField(verbose_name="Oturum No")),
                ("saat_baslangic", models.TimeField(verbose_name="Başlangıç")),
                ("saat_bitis",     models.TimeField(verbose_name="Bitiş")),
                ("sinav_turu",     models.CharField(
                    blank=True, default="", max_length=20,
                    choices=[("", "Normal"), ("Yazili", "Yazılı"), ("Uygulama", "Uygulama")],
                    verbose_name="Tür",
                )),
                ("ders_adi",       models.CharField(max_length=200, verbose_name="Ders Adı")),
                ("sinav",          models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="takvim",
                    to="sorumluluk.sorumlusinav",
                    verbose_name="Sınav",
                )),
            ],
            options={
                "verbose_name": "Takvim Kaydı",
                "verbose_name_plural": "Takvim Kayıtları",
                "ordering": ["tarih", "oturum_no", "ders_adi"],
                "unique_together": {("sinav", "tarih", "oturum_no", "ders_adi")},
            },
        ),

        # 2. Yeni SorumluSinavParametre tablosu
        migrations.CreateModel(
            name="SorumluSinavParametre",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("baslangic_tarihi",      models.DateField(verbose_name="Başlangıç Tarihi")),
                ("oturum_saatleri",       models.JSONField(
                    default=list,
                    verbose_name="Oturum Saatleri",
                    help_text='Örn: ["10:00-10:40","11:00-11:40"]',
                )),
                ("max_gunluk_sinav",      models.PositiveSmallIntegerField(default=2, verbose_name="Günlük Maks. Sınav")),
                ("slot_max_ders",         models.PositiveSmallIntegerField(default=6, verbose_name="Oturumda Maks. Ders")),
                ("tatil_tarihleri",       models.JSONField(
                    default=list,
                    verbose_name="Tatil Tarihleri",
                    help_text="GG.AA.YYYY formatında tarih listesi",
                )),
                ("hafta_sonu_haric",      models.BooleanField(default=True, verbose_name="Hafta Sonlarını Atla")),
                ("cift_oturumlu_dersler", models.JSONField(
                    default=list,
                    verbose_name="Çift Oturumlu Dersler",
                    help_text="SorumluDersHavuzu ID listesi",
                )),
                ("max_iter",              models.PositiveSmallIntegerField(default=500, verbose_name="Maks. İterasyon")),
                ("sinav",                 models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="parametreler",
                    to="sorumluluk.sorumlusinav",
                    verbose_name="Sınav",
                )),
            ],
            options={
                "verbose_name": "Sınav Parametresi",
                "verbose_name_plural": "Sınav Parametreleri",
            },
        ),

        # 3. SorumluOturmaPlani: mevcut unique_together ve oturum FK kaldır
        migrations.AlterUniqueTogether(
            name="sorumluoturmaplani",
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name="sorumluoturmaplani",
            name="oturum",
        ),

        # 4. SorumluOturmaPlani: yeni alanlar ekle
        migrations.AddField(
            model_name="sorumluoturmaplani",
            name="tarih",
            field=models.DateField(default="2000-01-01", verbose_name="Tarih"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sorumluoturmaplani",
            name="oturum_no",
            field=models.PositiveSmallIntegerField(default=1, verbose_name="Oturum No"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sorumluoturmaplani",
            name="saat_baslangic",
            field=models.TimeField(default="00:00", verbose_name="Başlangıç"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sorumluoturmaplani",
            name="saat_bitis",
            field=models.TimeField(default="00:00", verbose_name="Bitiş"),
            preserve_default=False,
        ),

        # 5. SorumluOturmaPlani: Meta güncelle
        migrations.AlterModelOptions(
            name="sorumluoturmaplani",
            options={
                "ordering": ["tarih", "oturum_no", "salon", "sira_no"],
                "verbose_name": "Oturma Planı Kaydı",
                "verbose_name_plural": "Oturma Planı",
            },
        ),
        migrations.AlterUniqueTogether(
            name="sorumluoturmaplani",
            unique_together={("sinav", "tarih", "oturum_no", "salon", "sira_no")},
        ),

        # 6. Eski tablolar: önce FK zincirindeki alt modeli sil
        migrations.DeleteModel(name="SorumluOturumDers"),
        migrations.DeleteModel(name="SorumluOturum"),
        migrations.DeleteModel(name="SorumluGun"),
    ]