from django.core.management.base import BaseCommand

from kurul.services.katalog import katalogu_yukle


class Command(BaseCommand):
    help = (
        "Varsayılan kurul/komisyon kataloğunu (kurul/fixtures/kurul_katalogu.json) yükler. "
        "Var olan türlere dokunmaz; --guncelle ile katalogdaki bilgilerle üzerine yazar."
    )

    def add_arguments(self, parser):
        parser.add_argument("--guncelle", action="store_true", help="Var olan türleri katalogla günceller.")

    def handle(self, *args, **opts):
        s = katalogu_yukle(guncelle=opts["guncelle"])
        self.stdout.write(self.style.SUCCESS(
            f"Eklenen: {s['eklenen']}, güncellenen: {s['guncellenen']}, atlanan: {s['atlanan']}"
        ))
