"""
Google Drive yedekleme entegrasyonu için bir kerelik, interaktif OAuth
yetkilendirmesi yapar (bkz. `yedekleme/services/gdrive_servisi.py`).

Bir tarayıcı açar (yerel bir geçici sunucu üzerinden), Google hesabınızla
giriş yapıp izin vermenizi ister; sonuçta oluşan token (erişim + yenileme
belirteci) `.env`'deki YEDEKLEME_GDRIVE_TOKEN yoluna kaydedilir.

Yalnızca tarayıcısı olan bir makineden çalıştırılabilir — sunucuda headless
çalıştırmak isterseniz, bu komutu yerel makinenizde çalıştırıp oluşan token
dosyasını sunucuya (chmod 600 ile) kopyalayın. Token bir kez oluştuktan
sonra otomatik yenilenir, bu komutu tekrar çalıştırmanız gerekmez.

Kullanım:
    python manage.py gdrive_yetkilendir
"""

from django.core.management.base import BaseCommand, CommandError

from yedekleme.services import gdrive_servisi
from yedekleme.services.yedek_servisi import YedekHatasi


class Command(BaseCommand):
    help = "Google Drive için bir kerelik interaktif OAuth yetkilendirmesi yapar."

    def handle(self, *args, **options):
        self.stdout.write("Tarayıcı açılacak — Google hesabınızla giriş yapıp izin verin...")
        try:
            token_yolu = gdrive_servisi.oauth_yetkilendir()
        except YedekHatasi as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Yetkilendirme tamamlandı, token kaydedildi: {token_yolu}")
        )
