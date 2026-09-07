"""Arka planda çalışan EBA QR websocket işçisi.

Django'nun senkron istek/yanıt döngüsü, EBA'nın uzun ömürlü websocket
bağlantısını doğrudan yönetemez (bkz. `ebagiris/services/eba_client.py`
modül docstring'i) — bu komut ayrı bir süreç olarak (geliştirmede elle,
üretimde systemd altında) sürekli çalışır, bekleyen her `EbaOturum`'u
(durum=bekliyor) veritabanından yoklayıp kendi websocket görevini başlatır.

Kullanım (geliştirme):
    python manage.py eba_ws_worker

Üretimde `ebaqr-greeter-service` (bkz. lightdm projesi) gibi bir systemd
servisi altında çalıştırılması beklenir; bu prototip aşamasında yalnızca
yönetim komutu olarak sağlanıyor.
"""
import asyncio

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from django.utils import timezone

from ebagiris.models import EbaOturum
from ebagiris.services import eba_client

YOKLAMA_ARALIGI_SN = 0.5
ESKI_OTURUM_OMRU_SN = 3600  # 1 saat sonra yarım kalmış oturum satırları silinir
TEMIZLIK_ARALIGI_SN = 300


@sync_to_async
def _bekleyen_id_leri_al():
    return list(
        EbaOturum.objects.filter(durum=EbaOturum.DURUM_BEKLIYOR).values_list("pk", flat=True)
    )


@sync_to_async
def _eski_oturumlari_temizle():
    sinir = timezone.now() - timezone.timedelta(seconds=ESKI_OTURUM_OMRU_SN)
    silinen, _ = EbaOturum.objects.filter(olusturma_zamani__lt=sinir).delete()
    return silinen


def _gorev_bitince(oturum_id, calisan_gorevler, stdout):
    def _geri_cagri(gorev):
        calisan_gorevler.pop(oturum_id, None)
        if not gorev.cancelled() and gorev.exception() is not None:
            stdout.write(f"[eba_ws_worker] oturum {oturum_id} hata ile bitti: {gorev.exception()!r}")

    return _geri_cagri


async def _dongu(stdout):
    # oturum_id -> asyncio.Task: yalnızca HÂLÂ ÇALIŞAN görevleri tutar (görev
    # bitince done-callback ile kendini çıkarır) — bir "işlenmiş id" kümesini
    # süreç ömrü boyunca büyütüp periyodik sıfırlamak yerine bu yaklaşım,
    # sıfırlama anıyla "hâlâ bekliyor" durumunun çakışıp aynı oturumun iki kez
    # başlatılması riskini baştan ortadan kaldırır.
    calisan_gorevler = {}
    son_temizlik = 0.0
    loop = asyncio.get_event_loop()
    while True:
        for oturum_id in await _bekleyen_id_leri_al():
            if oturum_id in calisan_gorevler:
                continue
            stdout.write(f"[eba_ws_worker] oturum {oturum_id} başlatılıyor")
            gorev = asyncio.create_task(eba_client.calistir(oturum_id))
            calisan_gorevler[oturum_id] = gorev
            gorev.add_done_callback(_gorev_bitince(oturum_id, calisan_gorevler, stdout))

        simdi = loop.time()
        if simdi - son_temizlik > TEMIZLIK_ARALIGI_SN:
            silinen = await _eski_oturumlari_temizle()
            if silinen:
                stdout.write(f"[eba_ws_worker] {silinen} eski oturum temizlendi")
            son_temizlik = simdi

        await asyncio.sleep(YOKLAMA_ARALIGI_SN)


class Command(BaseCommand):
    help = "EBA QR karekod websocket köprüsünü arka planda çalıştırır (Ctrl+C ile durur)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("EBA QR işçisi başlatıldı. Durdurmak için Ctrl+C."))
        try:
            asyncio.run(_dongu(self.stdout))
        except KeyboardInterrupt:
            self.stdout.write("Durduruldu.")
