from django.core.management.base import BaseCommand

from veriaktar.services.personel_import_service import PersonelIsleyici


class Command(BaseCommand):
    help = "Excel personel listesini içe aktarır"

    def handle(self, *args, **kwargs):
        isleyici = PersonelIsleyici(personel_path="personel.xlsx")
        isleyici.calistir()
        self.stdout.write(self.style.SUCCESS("Personel aktarıldı"))
