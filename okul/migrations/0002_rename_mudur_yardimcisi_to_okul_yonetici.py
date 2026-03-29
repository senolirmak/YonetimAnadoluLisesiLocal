from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("okul", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="MudurYardimcisi",
            new_name="OkulYonetici",
        ),
        migrations.AlterModelOptions(
            name="okulyonetici",
            options={
                "verbose_name": "Okul Yöneticisi",
                "verbose_name_plural": "Okul Yöneticileri",
            },
        ),
        migrations.AddField(
            model_name="okulyonetici",
            name="unvan",
            field=models.CharField(
                choices=[
                    ("okul_muduru", "Okul Müdürü"),
                    ("mudur_yardimcisi", "Müdür Yardımcısı"),
                ],
                default="mudur_yardimcisi",
                max_length=20,
                verbose_name="Unvan",
            ),
        ),
        migrations.AlterField(
            model_name="okulyonetici",
            name="user",
            field=models.OneToOneField(
                on_delete=models.deletion.CASCADE,
                related_name="okul_yonetici",
                to="auth.user",
                verbose_name="Kullanıcı",
            ),
        ),
        migrations.AlterField(
            model_name="okulyonetici",
            name="personel",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="okul_yonetici",
                to="nobet.nobetpersonel",
                verbose_name="Personel",
            ),
        ),
    ]
