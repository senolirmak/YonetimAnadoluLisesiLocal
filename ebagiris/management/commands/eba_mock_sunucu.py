"""Yerel geliştirme için sahte EBA QR websocket sunucusu — ÜRETİMDE KULLANILMAZ.

Kaynak: `home/senolirmak/Projeler/lightdm/tools/mock-eba-ws.py` (aynı
yazarın ebaqr-greeter projesi), Pardus'un gerçek eta-qr-login
`mock_service.py`'sinden (GPL-3.0+) uyarlanmıştır. Gerçek EBA sunucusuna
(qr-etap.eba.gov.tr — kapalı/resmî bir servis) internet erişimi olmadan,
uçtan uca akışı (QR göster → sahte doğrulama → EbaHesap eşleştirme → Django
girişi) test etmek içindir.

Kullanım:
    # 1) sahte sunucuyu başlat
    python manage.py eba_mock_sunucu --eba-id 12345678901 --ad-soyad "Ayşe Öğretmen"

    # 2) .env'de gerçek adres yerine bunu kullan
    EBA_QR_WS_URL=ws://127.0.0.1:8765/{token}

    # 3) işçiyi ayrı bir terminalde çalıştır
    python manage.py eba_ws_worker

`--eba-id` ile verilen kimlik, `ebagiris_hesap` tablosunda bir `EbaHesap`'a
önceden bağlıysa "EBA Karekod ile Giriş" akışı gerçek bir Personel'e/
kullanıcıya ulaşır (bkz. `ebagiris/views.py`); bağlı değilse "bu EBA hesabı
sisteme bağlı değil" mesajını test etmiş olursunuz. "Hesap Bağlama" akışını
test etmek için `--eba-id` vermeye gerek yoktur.
"""
import asyncio
import json
import time
import uuid

import websockets
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Yerel test için sahte EBA QR websocket sunucusu çalıştırır (üretimde KULLANILMAZ)."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8765)
        parser.add_argument(
            "--eba-id",
            default=None,
            help="Doğrulamada dönecek sahte EBA kimliği (verilmezse rastgele üretilir).",
        )
        parser.add_argument("--ad-soyad", default="Sınav ÖĞRETMEN")
        parser.add_argument(
            "--gecikme",
            type=float,
            default=3.0,
            help="QR üretildikten kaç saniye sonra 'doğrulandı' mesajı gönderilsin.",
        )

    def handle(self, *args, **options):
        eba_id = options["eba_id"] or str(uuid.uuid4().int)[:23]
        ad_soyad = options["ad_soyad"]
        gecikme = options["gecikme"]
        host, port = options["host"], options["port"]

        self.stdout.write(self.style.SUCCESS(
            f"Sahte EBA QR websocket sunucusu: ws://{host}:{port}/<token>"
        ))
        self.stdout.write(f"  doğrulanacak eba_id = {eba_id!r}")
        self.stdout.write(f"  doğrulanacak ad_soyad = {ad_soyad!r}")
        self.stdout.write(
            f".env dosyanıza ekleyin: EBA_QR_WS_URL=ws://{host}:{port}/{{token}}"
        )

        fake_validation = {
            "type": "validation",
            "status": "success",
            "user_data": {"uid": eba_id, "uname": ad_soyad, "utype": "TEACHER"},
        }

        async def handler(websocket):
            try:
                while True:
                    ham = await websocket.recv()
                    self.stdout.write(f"<<< {ham}")
                    qid = str(uuid.uuid4())
                    await websocket.send(json.dumps({
                        "uuid": qid,
                        "expire_at": int(time.time() + 60),
                    }))
                    await asyncio.sleep(gecikme)
                    await websocket.send(json.dumps(fake_validation))
                    await asyncio.sleep(5)
                    await websocket.close()
            except websockets.exceptions.ConnectionClosed:
                self.stdout.write("İstemci bağlantısı kapandı.")

        async def main():
            async with websockets.serve(handler, host, port):
                await asyncio.Future()

        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            self.stdout.write("\nKapatılıyor...")
