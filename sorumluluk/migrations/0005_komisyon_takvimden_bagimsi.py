from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sorumluluk", "0004_gorevlendirme"),
        ("okul", "0001_initial"),
    ]

    operations = [
        # Eski takvim-bağımlı tablo tamamen kaldırılır; yeni yapıda yeniden oluşturulur.
        migrations.DeleteModel(name="SorumluKomisyonUyesi"),
        migrations.CreateModel(
            name="SorumluKomisyonUyesi",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tarih", models.DateField(verbose_name="Tarih")),
                ("oturum_no", models.PositiveSmallIntegerField(verbose_name="Oturum No")),
                ("ders_adi", models.CharField(max_length=200, verbose_name="Ders Adı")),
                (
                    "sinav",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="komisyon_uyeler",
                        to="sorumluluk.sorumluSinav",
                        verbose_name="Sınav",
                    ),
                ),
                (
                    "uye1",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="okul.personel",
                        verbose_name="1. Komisyon Üyesi",
                    ),
                ),
                (
                    "uye2",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="okul.personel",
                        verbose_name="2. Komisyon Üyesi",
                    ),
                ),
            ],
            options={
                "verbose_name": "Komisyon Üyesi",
                "verbose_name_plural": "Komisyon Üyeleri",
                "ordering": ["tarih", "oturum_no", "ders_adi"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="SorumluKomisyonUyesi",
            unique_together={("sinav", "tarih", "oturum_no", "ders_adi")},
        ),
    ]
