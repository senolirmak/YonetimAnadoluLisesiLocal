"""Tahtaların APT deposu için imza anahtarını üretir (sunucuda bir kez).

Kurulumcu bunu kendisi çalıştırır. Elle (sunucuda, uygulamayı çalıştıran
kullanıcıyla — dosya ona ait olmalı):

    sudo -u akalsite env -C <PROJE_DIZINI> venv/bin/python manage.py \\
        tahta_apt_anahtari_olustur --settings=config.settings.production

Anahtar `tahta-deposu/imza-anahtari.json` dosyasına yazılır (yalnızca sahibi
okur, repoya girmez). Anahtar varsa komut hiçbir şeyi değiştirmez; ilk sürümün
kullandığı eski konumda (proje kökü) varsa yeni yerine taşınır. Anahtarı
değiştirmek (--zorla) depoyu tanıyan tahtaların güncelleme almasını keser: her
tahtaya paketin yeniden kurulması gerekir.
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
        yol = depo_anahtari.ANAHTAR_DOSYASI
        if yol.exists() and not zorla:
            self.stdout.write(f"Anahtar zaten var, değiştirilmedi: {yol}")
            return
        try:
            anahtar, uretildi = depo_anahtari.imza_anahtari_olustur(zorla=zorla)
        except depo_anahtari.AnahtarHatasi as hata:
            raise CommandError(str(hata)) from hata
        islem = "üretildi" if uretildi else f"eski konumdan taşındı ({depo_anahtari.ESKI_ANAHTAR_DOSYASI})"
        self.stdout.write(
            self.style.SUCCESS(
                f"APT depo anahtarı {islem}: {yol}\n"
                f"Parmak izi: {anahtar.parmak_izi.hex().upper()}"
            )
        )
        if uretildi:
            self.stdout.write(
                "Tahtalara bu anahtarı taşıyan paket bir kez kurulmalı (Tahtalar → Kurulum paketi). "
                "Anahtarı yedeğe almak için Yedekleme sayfasından bir medya yedeği alın."
            )
