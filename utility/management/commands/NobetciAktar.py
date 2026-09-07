import os
from io import BytesIO

from django.core.management.base import BaseCommand, CommandError

from veriaktar.services.nobet_import_service import NobetIsleyici


class Command(BaseCommand):
    help = "Excel nöbet listesini (..ÖğretmenNöbet.xlsx) içe aktarır"

    def add_arguments(self, parser):
        parser.add_argument("dosya_yolu", help="Nöbet Excel dosyasının yolu")
        parser.add_argument(
            "--uygulama-tarihi", default="2026/02/23", help="Uygulama tarihi (YYYY/AA/GG)"
        )

    def handle(self, *args, **options):
        dosya_yolu = options["dosya_yolu"]
        try:
            with open(dosya_yolu, "rb") as fh:
                dosya = BytesIO(fh.read())
        except OSError as exc:
            raise CommandError(f"Dosya okunamadı: {dosya_yolu} ({exc})") from exc
        dosya.name = os.path.basename(dosya_yolu)

        isleyici = NobetIsleyici(dosya=dosya, uygulama_tarihi=options["uygulama_tarihi"])
        isleyici.calistir()
        self.stdout.write(self.style.SUCCESS("Nöbetçiler aktarıldı"))
