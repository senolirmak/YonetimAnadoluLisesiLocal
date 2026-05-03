from decimal import Decimal

from django.core.management.base import BaseCommand

from ekders.models import GorevTipi

GOREV_TIPLERI = [
    {"kod": "mudur",           "ad": "Okul Müdürü",       "maas_karsiligi_haftalik": 2,  "hazirlik_katsayi": "0.00"},
    {"kod": "mudur_yardimcisi","ad": "Müdür Yardımcısı",  "maas_karsiligi_haftalik": 6,  "hazirlik_katsayi": "0.00"},
    {"kod": "brans_ogretmeni", "ad": "Öğretmen",           "maas_karsiligi_haftalik": 15, "hazirlik_katsayi": "0.10"},
    {"kod": "rehber_ogretmen", "ad": "Rehberlik",           "maas_karsiligi_haftalik": 18, "hazirlik_katsayi": "0.00"},
    {"kod": "ucretli_ogretmen","ad": "Ücretli Öğretmen",   "maas_karsiligi_haftalik": 0,  "hazirlik_katsayi": "0.10"},
]


class Command(BaseCommand):
    help = "Ek ders görev tiplerini oluşturur / günceller."

    def handle(self, *args, **options):
        for veri in GOREV_TIPLERI:
            obj, created = GorevTipi.objects.update_or_create(
                kod=veri["kod"],
                defaults={
                    "ad": veri["ad"],
                    "maas_karsiligi_haftalik": veri["maas_karsiligi_haftalik"],
                    "hazirlik_katsayi": Decimal(veri["hazirlik_katsayi"]),
                },
            )
            durum = "oluşturuldu" if created else "güncellendi"
            self.stdout.write(f"  {obj.ad:<25} {durum}")
        self.stdout.write(self.style.SUCCESS("Görev tipleri hazır."))
