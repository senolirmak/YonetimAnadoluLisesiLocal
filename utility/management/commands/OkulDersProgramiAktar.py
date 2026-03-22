from django.core.management.base import BaseCommand

from veriaktar.services.ders_programi_import_service import DersProgramiIsleyici


class Command(BaseCommand):
    help = "Excel ders programını içe aktarır"

    def handle(self, *args, **kwargs):
        isleyici = DersProgramiIsleyici(file_path="OOK11002_R01_222.XLS")
        isleyici.calistir()
        self.stdout.write(self.style.SUCCESS("Ders programı aktarıldı"))
