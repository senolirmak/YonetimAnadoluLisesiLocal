from django.core.management.base import BaseCommand

from veriaktar.services.nobet_import_service import NobetIsleyici


class Command(BaseCommand):
    help = "Excel nöbet listesini içe aktarır"

    def handle(self, *args, **kwargs):
        isleyici = NobetIsleyici(nobet_path="23SUBAT2026ÖğretmenNöbet.xlsx")
        isleyici.calistir()
        self.stdout.write(self.style.SUCCESS("Nöbetçiler aktarıldı"))
