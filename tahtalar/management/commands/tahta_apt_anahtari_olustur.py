"""Tahtaların APT deposu için imza anahtarını üretir (sunucuda bir kez).

Kullanım (sunucuda, uygulamayı çalıştıran kullanıcıyla):
    python manage.py tahta_apt_anahtari_olustur --settings=config.settings.production

Anahtar BASE_DIR/tahta-apt-imza-anahtari.json dosyasına yazılır (yalnızca
sahibi okur, repoya girmez). Anahtar varsa komut hiçbir şeyi değiştirmez.
Anahtarı değiştirmek (--zorla) depoyu tanıyan tahtaların güncelleme almasını
keser: her tahtaya paketin yeniden kurulması gerekir.
"""

from django.core.management.base import BaseCommand, CommandError

from tahtalar.services import depo_anahtari


class Command(BaseCommand):
    help = "Tahtaların akal-eta-yonetim APT deposu için imza anahtarını üretir."

    def add_arguments(self, parser):
        parser.add_argument(
            "--zorla",
            action="store_true",
            help="Var olan anahtarın yerine yenisini üret (tahtalara paket yeniden kurulmalı).",
        )

    def handle(self, *args, zorla, **options):
        try:
            anahtar = depo_anahtari.imza_anahtari_olustur(zorla=zorla)
        except depo_anahtari.AnahtarHatasi as hata:
            mevcut = depo_anahtari.ANAHTAR_DOSYASI.exists() and not zorla
            if mevcut:
                self.stdout.write(
                    f"Anahtar zaten var, değiştirilmedi: {depo_anahtari.ANAHTAR_DOSYASI}"
                )
                return
            raise CommandError(str(hata)) from hata
        self.stdout.write(
            self.style.SUCCESS(
                f"APT depo anahtarı üretildi: {depo_anahtari.ANAHTAR_DOSYASI}\n"
                f"Parmak izi: {anahtar.parmak_izi.hex().upper()}\n"
                "Tahtalara bu anahtarı taşıyan paket bir kez kurulmalı (Tahtalar → Kurulum paketi)."
            )
        )
