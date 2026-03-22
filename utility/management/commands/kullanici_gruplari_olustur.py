"""
Kullanıcı gruplarını ve örnek kullanıcıları oluşturur.

Kullanım:
    python manage.py kullanici_gruplari_olustur

Gruplar:
    - mudur_yardimcisi  : Nöbet dağıtım ve doldurma işlemlerini yapabilir
    - okul_muduru       : Sadece listeleri görüntüleyebilir
    - rehber_ogretmen   : Sadece listeleri görüntüleyebilir
    - disiplin_kurulu   : Sadece listeleri görüntüleyebilir
    - ogretmen          : Sadece listeleri görüntüleyebilir
"""

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

GRUPLAR = [
    ("mudur_yardimcisi", "Müdür Yardımcısı"),
    ("okul_muduru", "Okul Müdürü"),
    ("rehber_ogretmen", "Rehber Öğretmen"),
    ("disiplin_kurulu", "Disiplin Kurulu"),
    ("ogretmen", "Öğretmen"),
]


class Command(BaseCommand):
    help = "Nöbet sistemi kullanıcı gruplarını oluşturur"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ornek-kullanici",
            action="store_true",
            help="Her grup için örnek kullanıcı oluşturur (şifre: Nobet2024!)",
        )

    def handle(self, *args, **options):
        self.stdout.write("Kullanıcı grupları oluşturuluyor...\n")

        for group_name, display_name in GRUPLAR:
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"  [+] Grup oluşturuldu: {display_name} ({group_name})")
                )
            else:
                self.stdout.write(f"  [=] Grup zaten mevcut: {display_name} ({group_name})")

        if options["ornek_kullanici"]:
            self.stdout.write("\nÖrnek kullanıcılar oluşturuluyor...\n")
            ornek_sifre = "Nobet2024!"

            ornek_kullanicilar = [
                ("mudur_yardimcisi", "mudyrd", "Müdür", "Yardımcısı"),
                ("okul_muduru", "mudur", "Okul", "Müdürü"),
                ("rehber_ogretmen", "rehber", "Rehber", "Öğretmen"),
                ("disiplin_kurulu", "disiplin", "Disiplin", "Kurulu"),
                ("ogretmen", "ogretmen", "Öğretmen", "Kullanıcı"),
            ]

            for group_name, username, first_name, last_name in ornek_kullanicilar:
                if User.objects.filter(username=username).exists():
                    self.stdout.write(f"  [=] Kullanıcı zaten mevcut: {username}")
                    continue

                user = User.objects.create_user(
                    username=username,
                    password=ornek_sifre,
                    first_name=first_name,
                    last_name=last_name,
                )
                group = Group.objects.get(name=group_name)
                user.groups.add(group)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [+] Kullanıcı oluşturuldu: {username} / {ornek_sifre}  ({group_name})"
                    )
                )

        self.stdout.write(self.style.SUCCESS("\nTamamlandi!"))
        self.stdout.write("\nGrup bilgisi:")
        self.stdout.write(
            "  mudur_yardimcisi : Nöbet dağıtım, rotasyon, ders doldurma, devamsızlık işlemleri"
        )
        self.stdout.write(
            "  Diğer gruplar    : Haftalık nöbet listesi, günün nöbetçileri, ders doldurma listesi (sadece görüntüleme)"
        )
