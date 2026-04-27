import json

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin

from okul.models import OkulBilgi

from .models import DersSaati, Duyuru, Etkinlik, KioskAyar, MedyaIcerik


def _okul_adi():
    bilgi = OkulBilgi.objects.first()
    return bilgi.okul_adi if bilgi and bilgi.okul_adi else ""


@xframe_options_sameorigin
def index(request):
    """
    Ana Pano sayfasını gösterir. Gerekli tüm verileri toplayıp template'e gönderir.
    """
    now = timezone.now()
    # Django'nun weekday'i (Pazartesi=0) bizim modelimizdeki (Pazartesi=1) formata çevrilir.
    today_weekday = now.weekday() + 1

    # Bugünün aktif ders saatlerini al
    dersler_qs = DersSaati.objects.filter(aktif=True, gun=today_weekday).order_by("ders_no")

    # Ders başlangıç saatlerini "HH:MM" formatında listeye çevir
    ders_saatleri = [d.baslangic.strftime("%H:%M") for d in dersler_qs]

    # Ders süresini al (ilk dersin süresini varsayalım, yoksa 40dk)
    lesson_min = dersler_qs.first().sure_dk if dersler_qs.exists() else 40

    # Yayında olan aktif duyuruları al
    duyurular_qs = Duyuru.objects.filter(aktif=True).order_by("sira")
    yayindaki_duyurular = [d for d in duyurular_qs if d.yayinda_mi(now)]
    duyuru_metinleri = [d.metin for d in yayindaki_duyurular]

    # --- YENİ EKLENEN BÖLÜM: Medya İçeriklerini Al ---
    medya_qs = MedyaIcerik.objects.filter(aktif=True).order_by("sira")
    media_playlist = []
    for medya in medya_qs:
        media_playlist.append(
            {
                "url": medya.dosya.url,
                "type": medya.tur,
                "duration": medya.sure,
                "description": medya.aciklama,
                "title": medya.baslik,
            }
        )
    # ----------------------------------------------------

    context = {
        "SCHOOL_NAME": _okul_adi(),
        "DERSLER": json.dumps(ders_saatleri),
        "DUYURULAR": duyuru_metinleri,
        "DUYURULAR_JSON": json.dumps(duyuru_metinleri),
        "LESSON_MIN": lesson_min,
        "FLASH_MS": 900,
        "BLINK_ACTIVE_LESSON": "true",
        "MEDIA_PLAYLIST": json.dumps(media_playlist),
    }

    return render(request, "pano/index.html", context)


@xframe_options_sameorigin
def etkinlikler(request):
    """
    Etkinlikler sayfasını gösterir.
    """
    now = timezone.now()

    # Bugünün aktif ders saatlerini al (Badge durumu için gerekli)
    today_weekday = now.weekday() + 1
    dersler_qs = DersSaati.objects.filter(aktif=True, gun=today_weekday).order_by("ders_no")
    ders_saatleri = [d.baslangic.strftime("%H:%M") for d in dersler_qs]
    lesson_min = dersler_qs.first().sure_dk if dersler_qs.exists() else 40

    # 1. Devam Edenler (Şu an bu aralıkta olanlar)
    ongoing_qs = Etkinlik.objects.filter(aktif=True, baslangic__lte=now, bitis__gte=now).order_by(
        "baslangic"
    )

    # 2. Yaklaşanlar (Henüz başlamamış olanlar)
    upcoming_qs = Etkinlik.objects.filter(aktif=True, baslangic__gt=now).order_by("baslangic")

    def group_by_day(qs):
        grouped = {}
        for e in qs:
            local_start = timezone.localtime(e.baslangic)
            gun = local_start.date()
            if gun not in grouped:
                grouped[gun] = []
            grouped[gun].append(e)
        return grouped

    context = {
        "ongoing_events": ongoing_qs.exists(),
        "ongoing_grouped": group_by_day(ongoing_qs),
        "upcoming_events": upcoming_qs.exists(),
        "upcoming_grouped": group_by_day(upcoming_qs),
        "now": now,
        "SCHOOL_NAME": _okul_adi(),
        "DUYURULAR": [],
        "DUYURULAR_JSON": json.dumps([]),
        "DERSLER": json.dumps(ders_saatleri),
        "LESSON_MIN": lesson_min,
    }
    return render(request, "pano/etkinlikler.html", context)


@xframe_options_sameorigin
def config_api(request):
    """Duyuru ve medya listesini JSON olarak döner — pano.js her 60s'de çeker."""
    now = timezone.now()
    duyurular_qs = Duyuru.objects.filter(aktif=True).order_by("sira")
    announcements = [d.metin for d in duyurular_qs if d.yayinda_mi(now)]

    medya_qs = MedyaIcerik.objects.filter(aktif=True).order_by("sira")
    media_playlist = [
        {
            "url": m.dosya.url,
            "type": m.tur,
            "duration": m.sure,
            "title": m.baslik,
            "description": m.aciklama,
        }
        for m in medya_qs
    ]

    return JsonResponse({"announcements": announcements, "media_playlist": media_playlist})


def kiosk(request):
    """
    Kiosk modu için ana yönlendirici. Sayfalar arasında geçişi yönetir.
    """
    ayar = KioskAyar.objects.filter(aktif=True).first()

    if not ayar:
        # Ayar yoksa, varsayılan değerlerle bir ayar nesnesi oluştur
        ayar = KioskAyar()

    # Kiosk'ta dönecek sayfaların URL'lerini ve sürelerini al
    pages = [
        {"url": reverse("pano:index"), "duration": ayar.ana_sayfa_sure},
        {"url": reverse("pano:etkinlikler"), "duration": ayar.etkinlik_sure},
    ]

    context = {
        "pages": json.dumps(pages),
        "effect": ayar.efekt,
    }
    return render(request, "pano/kiosk.html", context)
