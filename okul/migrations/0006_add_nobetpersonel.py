"""
SeparateDatabaseAndState: NobetPersonel modelini nobet app'inden okul app'ine taşır.
Tablo adı nobet_personel olarak korunur; veritabanına dokunulmaz.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("okul", "0005_add_sinifsube"),
        ("nobet", "0019_remove_sinifsube"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="NobetPersonel",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "user",
                            models.OneToOneField(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="personel",
                                to=settings.AUTH_USER_MODEL,
                                verbose_name="Kullanıcı",
                            ),
                        ),
                        ("kimlikno", models.CharField(max_length=11, unique=True)),
                        ("adi_soyadi", models.CharField(max_length=100, unique=True)),
                        ("brans", models.CharField(max_length=50)),
                        (
                            "cinsiyet",
                            models.BooleanField(
                                choices=[(True, "Erkek"), (False, "Kadın")],
                                default=True,
                            ),
                        ),
                        ("nobeti_var", models.BooleanField(default=True)),
                        (
                            "gorev_tipi",
                            models.CharField(blank=True, max_length=50, null=True),
                        ),
                        ("sabit_nobet", models.BooleanField(default=False)),
                    ],
                    options={
                        "verbose_name": "Personel",
                        "verbose_name_plural": "Personel Listesi",
                        "db_table": "nobet_personel",
                    },
                ),
            ],
        ),
    ]
