"""MEB Lider'den dışa aktarılan tahta listesini (Excel) yükler.

Kullanım:
    python manage.py tahta_envanteri_yukle "/yol/Okulda Akıllı Tahtalar.xlsx"

Lider Id'ye göre ekler/günceller, tekrar çalıştırmak güvenlidir. Excel dosyası
okulun envanteridir; depoya eklenmez.
"""

from django.core.management.base import BaseCommand, CommandError

from tahtalar.services.envanter_import import EnvanterHatasi, envanteri_yukle


class Command(BaseCommand):
    help = "MEB Lider tahta listesini (Excel) Tahta envanterine yükler."

    def add_arguments(self, parser):
        parser.add_argument("dosya", help="Lider'den indirilen .xlsx dosyası")

    def handle(self, *args, dosya, **options):
        try:
            sonuc = envanteri_yukle(dosya)
        except EnvanterHatasi as hata:
            raise CommandError(str(hata)) from hata
        for hata in sonuc.hatalar:
            self.stderr.write(self.style.WARNING(hata))
        self.stdout.write(
            self.style.SUCCESS(
                f"{sonuc.eklenen} eklendi, {sonuc.guncellenen} güncellendi, "
                f"{sonuc.baglanan} kayıtlı tahta envanterle eşleşti, "
                f"{len(sonuc.hatalar)} satır atlandı."
            )
        )
