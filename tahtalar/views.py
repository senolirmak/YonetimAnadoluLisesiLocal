"""Tahtadaki akal-eta-yonetim uygulamasının konuştuğu JSON uç noktaları.

Kullanıcı oturumu yerine tahtaya özel token ile doğrulanır; bu yüzden CSRF
korumasına tabi değildir.
"""

import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from tahtalar.services import ajan_api

AZAMI_GOVDE = 16 * 1024


def _json_govde(request):
    if len(request.body) > AZAMI_GOVDE:
        return None
    try:
        veri = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return None
    return veri if isinstance(veri, dict) else None


def _token(request):
    baslik = request.headers.get("Authorization", "")
    tur, _, deger = baslik.partition(" ")
    return deger.strip() if tur == "Token" else ""


@csrf_exempt
@require_POST
def kayit(request):
    veri = _json_govde(request)
    if veri is None:
        return JsonResponse({"hata": "Geçersiz istek."}, status=400)
    try:
        tahta, token = ajan_api.tahta_kaydet(veri)
    except ajan_api.KayitHatasi as hata:
        return JsonResponse({"hata": str(hata)}, status=403)
    ajan_api.durum_guncelle(tahta, veri)
    return JsonResponse({"token": token, "tahta": tahta.ad})


@csrf_exempt
@require_POST
def durum(request):
    tahta = ajan_api.token_ile_tahta(_token(request))
    if tahta is None:
        return JsonResponse({"hata": "Yetkisiz."}, status=401)
    veri = _json_govde(request)
    if veri is None:
        return JsonResponse({"hata": "Geçersiz istek."}, status=400)
    ajan_api.sonuclari_isle(tahta, veri.get("sonuclar"))
    ajan_api.durum_guncelle(tahta, veri)
    return JsonResponse({"komutlar": ajan_api.bekleyen_komutlari_teslim_et(tahta)})
