from django.core.management.base import BaseCommand

from veriaktar.services.sinifsube_import_service import sinif_sube_kaydet

sinif_bilgileri = {
    9: ["A", "B", "C", "D", "E", "F"],
    10: ["A", "B", "C", "D", "E", "F", "G", "H", "İ"],
    11: ["A", "B", "C", "D", "E", "F", "G", "H"],
    12: ["A", "B", "C", "D", "E", "F", "G"],
}


class Command(BaseCommand):
    help = "Sınıf ve şube bilgilerini içe aktarır"

    def handle(self, *args, **kwargs):
        sinif_sube_kaydet(sinif_bilgileri)
        self.stdout.write(self.style.SUCCESS("Sınıf Şube Bilgisi aktarıldı"))
