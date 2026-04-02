from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("sinav", "0048_add_oturmaplani_gozetmen_fk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="oturmaplani",
            name="gozetmen",
        ),
    ]
