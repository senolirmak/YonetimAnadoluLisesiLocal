import threading
import traceback
import uuid
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from dersprogrami.models import DersProgrami
from ogrenci.models import Ogrenci as OgrenciModel
from okul.auth import ust_yonetici_required
from okul.models import OkulBilgi
from ortaksinav_engine import (
    CONFIG,
    oturma_planlarini_olustur,
    subeders_guncelle,
    takvim_olustur,
    temel_verileri_olustur,
    verileri_aktar,
)
from sinav.services.config_builder import config_uygula
from sinav.services.sinav_ozet import db_ozeti, gozetmen_ozeti_hesapla, sinav_takvim_araliklari
from sinav.services.takvim_duzenleme import (
    onizleme_oturumlarini_yeniden_numarala,
    takvim_oturumlarini_yeniden_numarala,
    takvimi_onayla,
)
from sinav.services.takvim_slot import slot_temizle

from .forms import AlgoritmaForm, MazeretSinavForm, SinavBilgisiForm
from .models import (
    AlgoritmaParametreleri,
    DersAyarlariJSON,
    DisVeri,
    MazeretBelgeTeslim,
    MazeretOgrenci,
    MazeretOturmaPlani,
    MazeretOturum,
    MazeretOturumDers,
    MazeretSinav,
    OturmaPlani,
    SinavBilgisi,
    SinavSalonYoklama,
    Takvim,
    TakvimUretim,
)

# ---------------------------------------------------------------
# Bellekte gorev durumu
# ---------------------------------------------------------------
_TASKS: dict = {}
_TASKS_LOCK = threading.Lock()


def _new_task() -> str:
    task_id = uuid.uuid4().hex
    with _TASKS_LOCK:
        _TASKS[task_id] = {"logs": [], "done": False, "error": False, "cancel": False}
    return task_id


def _log(task_id: str, msg: str):
    with _TASKS_LOCK:
        _TASKS[task_id]["logs"].append(msg)


def _finish(task_id: str, error: bool = False):
    with _TASKS_LOCK:
        _TASKS[task_id]["done"] = True
        _TASKS[task_id]["error"] = error


# ---------------------------------------------------------------
# Yardimci fonksiyonlar
# ---------------------------------------------------------------
def _aktif_sinav():
    return SinavBilgisi.objects.filter(aktif=True).first()


def _get_ayarlar(sinav) -> dict:
    """Aktif sinava ait ders ayarlari JSON verisini döndürür."""
    if sinav is None:
        return {}
    obj, _ = DersAyarlariJSON.objects.get_or_create(sinav=sinav)
    return dict(obj.veri) if obj.veri else {}


def _save_ayarlar(sinav, veri: dict):
    """Ders ayarlari JSON verisini kaydeder."""
    obj, _ = DersAyarlariJSON.objects.get_or_create(sinav=sinav)
    obj.veri = veri
    obj.save()


def _kurulum_durumu():
    from okul.models import SinifSube
    okul = OkulBilgi.get()
    okul_tamam = bool(okul.okul_adi.strip() and okul.okul_kodu.strip())
    veri_tamam = SinifSube.objects.exists()
    return {
        "okul_tamam":    okul_tamam,
        "veri_tamam":    veri_tamam,
        "kurulum_tamam": okul_tamam and veri_tamam,
    }


def _dosya_durumu(request):
    """DB-first modelde dosya durumu artık kullanılmamaktadır."""
    return {
        "ogrenci_dosya_adi": "",
        "program_dosya_adi": "",
        "uygulama_tarihi":   "",
    }


def _alg_form_initial(request):
    # DB birincil kaynak; yoksa session'a bak
    aktif = _aktif_sinav()
    prm = AlgoritmaParametreleri.objects.filter(sinav=aktif).first() if aktif else None
    if prm:
        initial = prm.to_session_dict()
        if not initial.get("baslangic_tarih"):
            initial["baslangic_tarih"] = request.session.get(
                "ortaksinav_config", {}
            ).get("baslangic_tarih", "2025-01-06")
    else:
        saved = request.session.get("ortaksinav_config", {})
        initial = {
            "baslangic_tarih":   saved.get("baslangic_tarih",   "2025-01-06"),
            "oturum_saatleri":   saved.get("oturum_saatleri",   "08:50,10:30,12:10,13:35,14:25"),
            "tatil_gunleri":     saved.get("tatil_gunleri",     ""),
            "time_limit_phase1": saved.get("time_limit_phase1", 300),
            "time_limit_phase2": saved.get("time_limit_phase2", 120),
            "max_extra_days":    saved.get("max_extra_days",    10),
            "kelebek_dagitim":   saved.get("kelebek_dagitim",   True),
            "max_sinav_per_gun": saved.get("max_sinav_per_gun", 2),
        }
    return AlgoritmaForm(initial=initial)


# ---------------------------------------------------------------
# Ana sayfa – dashboard
# ---------------------------------------------------------------
@login_required
def index(request):
    # Aktif sinav yoksa en yenisini otomatik aktif yap
    aktif = _aktif_sinav()
    if aktif is None:
        yeni = SinavBilgisi.objects.first()
        if yeni:
            yeni.aktif_yap()
            aktif = yeni

    kurulum = _kurulum_durumu()
    db = db_ozeti()
    dosya = _dosya_durumu(request)
    liste = SinavBilgisi.objects.all()
    takvim_araliklari = sinav_takvim_araliklari(liste)
    for s in liste:
        s.otomatik_baslangic, s.otomatik_bitis = takvim_araliklari.get(s.pk, (None, None))
    liste_formlar = [(s, SinavBilgisiForm(instance=s)) for s in liste]
    return render(request, "sinav/index.html", {
        "aktif_sinav":   aktif,
        "liste_formlar": liste_formlar,
        "db_ozeti":      db,
        **kurulum,
        **dosya,
    })


# ---------------------------------------------------------------
# Veri Yukleme sayfasi
# ---------------------------------------------------------------
def _veri_yukle_ctx(request):
    aktif = _aktif_sinav()
    dis_veri = DisVeri.objects.filter(sinav=aktif)[:20]
    return {
        "aktif_sinav":     aktif,
        "sinav_listesi":   SinavBilgisi.objects.all(),
        "yeni_sinav_form": SinavBilgisiForm(),
        "dis_veri_gecmis": dis_veri,
        "ogrenci_sayisi":  OgrenciModel.objects.count(),
        "program_sayisi":  DersProgrami.objects.count(),
    }


@login_required
def veri_yukle_sayfasi(request):
    okul = OkulBilgi.get()
    if not bool(okul.okul_adi.strip() and okul.okul_kodu.strip()):
        messages.error(request, "Veri yüklemeden önce Okul Bilgilerini doldurun.")
        return redirect("sinav:sinav_bilgisi_listesi")
    return render(request, "sinav/veri_yukle.html", _veri_yukle_ctx(request))


def _veri_yukle_calistir(request):
    """Adim 0+1 calistirir (DB-first), ders_ayarlari'na yonlendirir."""
    from ortaksinav_engine.services.veri_import import VeriImportService

    aktif_sinav = _aktif_sinav()
    config_uygula(request.session.get("ortaksinav_config", {}))
    svc = VeriImportService(CONFIG)
    svc.temel_verileri_olustur()
    if aktif_sinav:
        svc.verileri_aktar(aktif_sinav)
    else:
        messages.info(request, "DersHavuzu güncellendi. Öğrenci ve ders verisi için önce sınav oluşturun.")

    messages.success(request, "Veri eşitleme tamamlandı.")
    return redirect("sinav:ders_ayarlari")


@require_POST
def veri_yukle(request):
    """DB-first veri eşitleme: Excel yüklemesi gerekmez."""
    okul = OkulBilgi.get()
    if not bool(okul.okul_adi.strip() and okul.okul_kodu.strip()):
        messages.error(request, "Veri yüklemeden önce Okul Bilgilerini doldurun.")
        return redirect("sinav:sinav_bilgisi_listesi")
    try:
        return _veri_yukle_calistir(request)
    except Exception as e:
        messages.error(request, f"Veri eşitleme hatası: {e}")
        messages.warning(request, traceback.format_exc())
        return redirect("sinav:veri_yukle_sayfasi")


@require_POST
def veri_yukle_onayla(request):
    """DB-first modelde onay adımı yoktur; doğrudan eşitlemeye yönlendir."""
    return redirect("sinav:veri_yukle")


# ---------------------------------------------------------------
# Sınav Bilgisi – Hizli aktif yap (next destekli)
# ---------------------------------------------------------------
@require_POST
def sinav_bilgisi_aktif_yap(request, pk: int):
    obj = SinavBilgisi.objects.get(pk=pk)
    obj.aktif_yap()

    # Bu sınavın kayıtlı algoritma parametrelerini varsa session'a yükle
    prm = AlgoritmaParametreleri.objects.filter(sinav=obj).first()
    if prm:
        cfg = request.session.get("ortaksinav_config", {})
        cfg.update(prm.to_session_dict())
        request.session["ortaksinav_config"] = cfg
        request.session.modified = True

    messages.success(request, f'"{obj}" aktif sınav olarak ayarlandı.')
    next_url = request.POST.get("next", "")
    if next_url == "veri":
        return redirect("sinav:veri_yukle_sayfasi")
    if next_url == "index":
        return redirect("sinav:index")
    return redirect("sinav:sinav_bilgisi_listesi")


@login_required
def takvim_uretim_aktif_yap(request, pk: int):
    """Seçili TakvimUretim'i aktif yap → öğretmen sayfaları bu üretime göre güncellenir."""
    uretim = get_object_or_404(TakvimUretim, pk=pk)
    uretim.aktif_yap()
    messages.success(request, f"Takvim üretimi ({uretim.uretim_tarihi:%d.%m.%Y %H:%M}) aktif yapıldı.")
    return redirect(f"{reverse('sinav:pdf_rapor')}?uretim_pk={pk}")


@require_POST
@login_required
def admin_force_aktif_toggle(request):
    """Admin: sınav saati koşulunu oturum boyunca aç/kapat."""
    from sinav.utils import AdminOverride
    if not request.user.is_superuser:
        return JsonResponse({"error": "Yetkisiz işlem."}, status=403)
    AdminOverride.toggle(request)
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)


@require_POST
@login_required
def slot_serbest_birak(request):
    """Staff/Superuser: belirtilen slot için OturmaUretim + OturmaPlani + SinavSalonYoklama kayıtlarını sil."""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({"error": "Yetkisiz işlem."}, status=403)

    uretim_pk = request.POST.get("uretim_pk")
    tarih     = request.POST.get("tarih")
    saat      = request.POST.get("saat")
    oturum    = request.POST.get("oturum")

    if not all([uretim_pk, tarih, saat, oturum]):
        return JsonResponse({"error": "Eksik parametre."}, status=400)

    uretim = get_object_or_404(TakvimUretim, pk=uretim_pk)
    sonuc = slot_temizle(uretim, tarih, saat, oturum, takvim_de_sil=False)

    messages.success(
        request,
        f"Slot serbest bırakıldı ({tarih} {saat} Ot.{oturum}) — {sonuc['op_sayisi']} oturma planı silindi."
    )
    return redirect(f"{reverse('sinav:pdf_rapor')}?uretim_pk={uretim_pk}")


@require_POST
@login_required
def takvim_slot_sil(request):
    """Staff/Superuser: belirtilen slotu takvimden tamamen sil
    (OturmaPlani + OturmaUretim + Takvim + SinavSalonYoklama)."""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({"error": "Yetkisiz işlem."}, status=403)

    uretim_pk = request.POST.get("uretim_pk")
    tarih     = request.POST.get("tarih")
    saat      = request.POST.get("saat")
    oturum    = request.POST.get("oturum")

    if not all([uretim_pk, tarih, saat, oturum]):
        return JsonResponse({"error": "Eksik parametre."}, status=400)

    uretim = get_object_or_404(TakvimUretim, pk=uretim_pk)
    sonuc = slot_temizle(uretim, tarih, saat, oturum, takvim_de_sil=True)

    messages.success(
        request,
        f"Slot takvimden silindi ({tarih} {saat} Ot.{oturum}) — {sonuc['takvim_sayisi']} takvim kaydı kaldırıldı."
    )
    return redirect(f"{reverse('sinav:pdf_rapor')}?uretim_pk={uretim_pk}")


@login_required
def gozetmen_ozet(request):
    """Aktif TakvimUretim'deki tüm gözetmenler + Sınıf Listesi PDF öğretmenlerini listeler."""
    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    gozetmenler, siniflistesi_map = gozetmen_ozeti_hesapla(aktif_uretim)

    return render(request, "sinav/gozetmen_ozet.html", {
        "aktif_sinav":      aktif_sinav,
        "aktif_uretim":     aktif_uretim,
        "gozetmenler":      gozetmenler,
        "siniflistesi_map": siniflistesi_map,
    })


# ---------------------------------------------------------------
# Takvim sayfasi context + view
# ---------------------------------------------------------------
def _takvim_ctx(request, alg_form=None):
    from sinav.models import SubeDers, Takvim, TakvimUretim
    if alg_form is None:
        alg_form = _alg_form_initial(request)
    aktif = _aktif_sinav()
    son_uretim    = TakvimUretim.objects.filter(sinav=aktif).first() if aktif else None
    aktif_uretim  = TakvimUretim.objects.filter(sinav=aktif, aktif=True).first() if aktif else None
    takvim_sayisi = Takvim.objects.filter(sinav=aktif).count()
    return {
        "aktif_sinav":       aktif,
        "alg_form":          alg_form,
        "alg_acik":          bool(alg_form.errors),
        "sube_ders_sayisi":  SubeDers.objects.count(),
        "takvim_sayisi":     takvim_sayisi,
        "aktif_uretim":      aktif_uretim,
        "onizleme_mevcut":   bool(son_uretim and son_uretim.onizleme_verisi is not None),
    }


@login_required
def takvim_sayfasi(request):
    return render(request, "sinav/takvim.html", _takvim_ctx(request))


@login_required
def takvim_onizleme(request):
    from collections import defaultdict

    from sinav.models import Takvim, TakvimUretim
    aktif = _aktif_sinav()
    son_uretim = TakvimUretim.objects.filter(sinav=aktif).first() if aktif else None

    # Geçmiş sayfasından belirli bir üretim seçildiyse onu kullan
    uretim_pk = request.GET.get("uretim_pk")
    if uretim_pk:
        try:
            son_uretim = TakvimUretim.objects.get(pk=uretim_pk)
        except TakvimUretim.DoesNotExist:
            pass

    if son_uretim and son_uretim.onizleme_verisi is not None:
        kayitlar = son_uretim.onizleme_verisi
        for i, r in enumerate(kayitlar):
            r["idx"] = i
        onaylandi = False
    elif aktif:
        # Takvim onaylanmış: önce aktif=True üretimi dene, yoksa en son üretimi kullan
        aktif_uretim = TakvimUretim.objects.filter(sinav=aktif, aktif=True).first()
        uretim_goster = aktif_uretim or son_uretim
        qs = (Takvim.objects.filter(uretim=uretim_goster).select_related("ders")
              if uretim_goster else Takvim.objects.none())
        if not qs.exists():
            messages.error(request, "Önizleme verisi bulunamadı. Önce takvimi oluşturun.")
            return redirect("sinav:takvim_sayfasi")
        kayitlar = [
            {
                "pk":      t.pk,
                "Tarih":   t.tarih.strftime("%Y-%m-%d"),
                "Saat":    t.saat,
                "Oturum":  t.oturum,
                "Ders":    t.ders_tam_adi,
                "Subeler": t.subeler,
            }
            for t in qs
        ]
        onaylandi = True
    else:
        messages.error(request, "Önizleme verisi bulunamadı. Önce takvimi oluşturun.")
        return redirect("sinav:takvim_sayfasi")

    gun_map = defaultdict(list)
    for r in kayitlar:
        gun_map[r["Tarih"]].append(r)
    gunler = [{"tarih": t, "satirlar": sorted(ss, key=lambda x: x["Oturum"])}
              for t, ss in sorted(gun_map.items())]
    return render(request, "sinav/takvim_onizleme.html", {
        "aktif_sinav": aktif,
        "gunler":      gunler,
        "toplam":      len(kayitlar),
        "gun_sayisi":  len(gunler),
        "onaylandi":   onaylandi,
    })


@require_POST
def takvim_onayla(request):
    from sinav.models import TakvimUretim
    aktif_sinav = _aktif_sinav()
    uretim = TakvimUretim.objects.filter(sinav=aktif_sinav).order_by("-uretim_tarihi").first()
    if not uretim or uretim.onizleme_verisi is None:
        messages.error(request, "Önizleme verisi bulunamadı.")
        return redirect("sinav:takvim_sayfasi")

    kayit_sayisi = takvimi_onayla(aktif_sinav, uretim)
    messages.success(request, f"Takvim onaylandı: {kayit_sayisi} kayıt DB'ye kaydedildi.")
    from_param = request.POST.get("from", "")
    from django.urls import reverse
    url = reverse("sinav:takvim_onizleme") + (f"?from={from_param}" if from_param else "")
    return redirect(url)


@require_POST
def takvim_onizleme_guncelle(request):
    """Onaylanmamış önizleme JSON'undaki tarih/saat değişikliklerini uygular."""
    from datetime import datetime as dt

    from sinav.models import TakvimUretim
    aktif_sinav = _aktif_sinav()
    uretim = TakvimUretim.objects.filter(sinav=aktif_sinav).order_by("-uretim_tarihi").first()
    if not uretim or uretim.onizleme_verisi is None:
        messages.error(request, "Önizleme verisi bulunamadı.")
        return redirect("sinav:takvim_onizleme")

    kayitlar = uretim.onizleme_verisi
    guncellenen = 0
    for i, r in enumerate(kayitlar):
        tarih_str = request.POST.get(f"tarih_idx_{i}", "").strip()
        saat_str  = request.POST.get(f"saat_idx_{i}", "").strip()
        changed = False
        try:
            if tarih_str:
                dt.strptime(tarih_str, "%Y-%m-%d")  # format kontrolü
                if tarih_str != r.get("Tarih"):
                    r["Tarih"] = tarih_str
                    changed = True
            if saat_str and saat_str != r.get("Saat"):
                r["Saat"] = saat_str
                changed = True
        except (ValueError, TypeError):
            continue
        if changed:
            guncellenen += 1

    # Oturum numaralarını Tarih+Saat sıralamasına göre yeniden hesapla
    onizleme_oturumlarini_yeniden_numarala(kayitlar)

    uretim.onizleme_verisi = kayitlar
    uretim.save(update_fields=["onizleme_verisi"])
    messages.success(request, f"{guncellenen} kayıt güncellendi." if guncellenen else "Güncelleme kaydedildi.")
    from_param = request.POST.get("from", "")
    from django.urls import reverse
    url = reverse("sinav:takvim_onizleme") + (f"?from={from_param}" if from_param else "")
    return redirect(url)


def takvim_ders_duzenle(request):
    """Ders bazında tarih/saat düzenleme ekranı.

    GET  → formu göster (preview veya onaylı mod)
    POST → modu tespit edip ilgili kaydetme view'ına yönlendir
    """
    from sinav.models import Takvim, TakvimUretim

    aktif = _aktif_sinav()
    son_uretim = TakvimUretim.objects.filter(sinav=aktif).order_by("-uretim_tarihi").first() if aktif else None

    if not son_uretim:
        messages.error(request, "Aktif sınav veya üretim bulunamadı.")
        return redirect("sinav:takvim_sayfasi")

    # ── Mod tespiti ─────────────────────────────────────────────────────────
    if son_uretim.onizleme_verisi is not None:
        onaylandi = False
        kayitlar_raw = son_uretim.onizleme_verisi
        satirlar = [
            {
                "idx":       i,
                "ders":      r.get("Ders", ""),
                "tarih":     r.get("Tarih", ""),
                "saat":      r.get("Saat", ""),
                "subeler":   r.get("Subeler", ""),
            }
            for i, r in enumerate(kayitlar_raw)
        ]
    else:
        aktif_uretim = TakvimUretim.objects.filter(sinav=aktif, aktif=True).first()
        if not aktif_uretim:
            messages.error(request, "Onaylı aktif üretim bulunamadı.")
            return redirect("sinav:takvim_onizleme")
        onaylandi = True
        qs = Takvim.objects.filter(uretim=aktif_uretim).select_related("ders").order_by("ders__ders_adi", "tarih", "saat")
        satirlar = [
            {
                "pk":      t.pk,
                "ders":    t.ders_tam_adi,
                "tarih":   t.tarih.strftime("%Y-%m-%d"),
                "saat":    t.saat,
                "subeler": t.subeler,
            }
            for t in qs
        ]

    # Preview modunda ders adına göre sırala
    if not onaylandi:
        satirlar.sort(key=lambda x: x["ders"].lower())

    if request.method == "POST":
        if onaylandi:
            return takvim_guncelle(request)
        else:
            return takvim_onizleme_guncelle(request)

    return render(request, "sinav/takvim_ders_duzenle.html", {
        "aktif_sinav": aktif,
        "satirlar":    satirlar,
        "onaylandi":   onaylandi,
    })


@require_POST
def takvim_onizleme_iptal(request):
    """Önizleme taslağını temizler ve Takvim (ILP) sayfasına döner."""
    aktif_sinav = _aktif_sinav()
    from sinav.models import TakvimUretim
    uretim = TakvimUretim.objects.filter(sinav=aktif_sinav).order_by("-uretim_tarihi").first()
    if uretim and uretim.onizleme_verisi is not None:
        uretim.onizleme_verisi = None
        uretim.save(update_fields=["onizleme_verisi"])
    return redirect("sinav:takvim_sayfasi")


@require_POST
def takvim_guncelle(request):
    """Takvim Formu'ndan gelen tarih/saat düzenlemelerini DB'ye yazar.
    Kayıt sonrası oturum numaraları gün bazında otomatik yeniden hesaplanır."""
    from datetime import datetime as dt

    from sinav.models import Takvim as TakvimModel
    aktif_sinav = _aktif_sinav()
    if not aktif_sinav:
        messages.error(request, "Aktif sınav bulunamadı.")
        return redirect("sinav:takvim_onizleme")

    from sinav.models import TakvimUretim
    aktif_uretim = TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
    kayitlar = list(TakvimModel.objects.filter(uretim=aktif_uretim))
    guncellenen = 0
    for t in kayitlar:
        tarih_str = request.POST.get(f"tarih_{t.pk}", "").strip()
        saat_str  = request.POST.get(f"saat_{t.pk}", "").strip()
        changed = False
        try:
            if tarih_str:
                yeni_tarih = dt.strptime(tarih_str, "%Y-%m-%d").date()
                if yeni_tarih != t.tarih:
                    t.tarih = yeni_tarih
                    changed = True
            if saat_str and saat_str != t.saat:
                t.saat = saat_str
                changed = True
        except (ValueError, TypeError):
            continue
        if changed:
            t.save(update_fields=["tarih", "saat"])
            guncellenen += 1

    # Oturum numaralarini gun bazinda yeniden hesapla
    takvim_oturumlarini_yeniden_numarala(aktif_uretim)

    messages.success(request, f"{guncellenen} kayıt güncellendi, oturum numaraları yenilendi.")
    from_param = request.POST.get("from", "")
    from django.urls import reverse
    url = reverse("sinav:takvim_onizleme") + (f"?from={from_param}" if from_param else "")
    return redirect(url)


@require_POST
def parametre_kaydet(request):
    form = AlgoritmaForm(request.POST)
    if not form.is_valid():
        return render(request, "sinav/takvim.html", _takvim_ctx(request, alg_form=form))

    cfg = request.session.get("ortaksinav_config", {})
    cfg["baslangic_tarih"]   = str(form.cleaned_data["baslangic_tarih"])
    cfg["oturum_saatleri"]   = form.cleaned_data["oturum_saatleri"]
    cfg["tatil_gunleri"]     = form.cleaned_data.get("tatil_gunleri", "")
    cfg["time_limit_phase1"] = form.cleaned_data["time_limit_phase1"]
    cfg["time_limit_phase2"] = form.cleaned_data["time_limit_phase2"]
    cfg["max_extra_days"]    = form.cleaned_data["max_extra_days"]
    cfg["kelebek_dagitim"]   = form.cleaned_data.get("kelebek_dagitim", True)
    cfg["max_sinav_per_gun"] = form.cleaned_data.get("max_sinav_per_gun", 2)
    request.session["ortaksinav_config"] = cfg
    request.session.modified = True

    # Aktif sınavın parametrelerini DB'ye de kaydet
    aktif = _aktif_sinav()
    if aktif:
        AlgoritmaParametreleri.objects.update_or_create(
            sinav=aktif,
            defaults={
                "baslangic_tarih":   form.cleaned_data["baslangic_tarih"],
                "oturum_saatleri":   form.cleaned_data["oturum_saatleri"],
                "tatil_gunleri":     form.cleaned_data.get("tatil_gunleri", ""),
                "time_limit_phase1": form.cleaned_data["time_limit_phase1"],
                "time_limit_phase2": form.cleaned_data["time_limit_phase2"],
                "max_extra_days":    form.cleaned_data["max_extra_days"],
                "kelebek_dagitim":   form.cleaned_data.get("kelebek_dagitim", True),
                "max_sinav_per_gun": form.cleaned_data.get("max_sinav_per_gun", 2),
            },
        )

    messages.success(request, "Algoritma parametreleri kaydedildi.")
    return redirect("sinav:takvim_sayfasi")


# ---------------------------------------------------------------
# Oturum Planlari sayfasi
# ---------------------------------------------------------------
# ---------------------------------------------------------------
# A4 Raporlar sayfasi
# ---------------------------------------------------------------
@login_required
def takvim_gecmisi(request):
    """Üretilen takvimlerin listesi: aktif sınava ait üretimler."""
    from django.db.models import Count

    from sinav.models import TakvimUretim
    aktif = _aktif_sinav()
    kayitlar = (
        TakvimUretim.objects
        .filter(sinav=aktif)
        .select_related("sinav")
        .annotate(sinav_takvim_sayisi=Count("takvimler_uretim"))
        .order_by("-uretim_tarihi")
    ) if aktif else TakvimUretim.objects.none()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif, aktif=True).first()
        if aktif else None
    )
    return render(request, "sinav/takvim_gecmisi.html", {
        "kayitlar": kayitlar,
        "aktif_sinav": aktif,
        "aktif_uretim": aktif_uretim,
    })


@login_required
def pdf_rapor(request):
    """PDF rapor üretim sayfası: seçili TakvimUretim'e bağlı takvim verilerini gösterir."""
    from collections import defaultdict

    from sinav.models import OturmaUretim, Takvim, TakvimUretim

    # Belirli üretim seçilmişse onu kullan; yoksa aktif üretimi bul
    uretim_pk = request.GET.get("uretim_pk")
    if uretim_pk:
        try:
            secili_uretim = TakvimUretim.objects.select_related("sinav").get(pk=uretim_pk)
        except TakvimUretim.DoesNotExist:
            messages.error(request, "Seçilen üretim bulunamadı.")
            return redirect("sinav:takvim_gecmisi")
    else:
        aktif = _aktif_sinav()
        secili_uretim = (
            TakvimUretim.objects.filter(sinav=aktif, aktif=True).select_related("sinav").first()
            if aktif else None
        )
    if not secili_uretim:
        messages.error(request, "PDF rapor için önce Takvim Geçmişi'nden bir takvim seçin.")
        return redirect("sinav:takvim_gecmisi")

    aktif = secili_uretim.sinav

    # Eski kayıtları (uretim=None) bu üretimle ilişkilendir
    Takvim.objects.filter(sinav=aktif, uretim__isnull=True).update(uretim=secili_uretim)

    takvim_kayitlari = (
        Takvim.objects
        .filter(uretim=secili_uretim)
        .select_related("ders")
        .order_by("tarih", "saat", "oturum", "ders__ders_adi")
    )

    # Oturum bazında gruplama
    session_map = defaultdict(list)
    for t in takvim_kayitlari:
        session_map[(t.tarih, t.saat, t.oturum)].append(
            t.ders.ders_adi if t.ders else ""
        )

    gun_map = defaultdict(list)
    for (tarih, saat, oturum), dersler in sorted(session_map.items()):
        gun_map[tarih].append({
            "tarih_str": tarih.strftime("%Y-%m-%d"),
            "saat":      str(saat),
            "oturum":    oturum,
            "dersler":   dersler,
        })

    takvim_degisti = secili_uretim.oturma_sifirla
    # Yalnızca bu üretimin OturmaUretim kayıtları
    mevcut_ou = {
        (ou.tarih, ou.saat, ou.oturum): ou
        for ou in OturmaUretim.objects.filter(takvim_uretim=secili_uretim)
    }
    gunler = []
    for tarih, oturumlar in sorted(gun_map.items()):
        for ot in oturumlar:
            ou = mevcut_ou.get((tarih, ot["saat"], ot["oturum"]))
            ot["oturma_mevcut"] = ou is not None
            ot["uretim_pk"] = secili_uretim.pk
        gunler.append({"tarih": tarih, "oturumlar": oturumlar})
    toplam_oturum = sum(len(g["oturumlar"]) for g in gunler)

    # Aynı sınavın diğer üretimleri (selector için)
    diger_uretimler = (
        TakvimUretim.objects
        .filter(sinav=aktif)
        .order_by("-uretim_tarihi")
    ) if aktif else []

    okul = OkulBilgi.get()
    return render(request, "sinav/pdf_rapor.html", {
        "aktif_sinav":      aktif,
        "secili_uretim":    secili_uretim,
        "okul":             okul,
        "gunler":           gunler,
        "toplam_oturum":    toplam_oturum,
        "gun_sayisi":       len(gunler),
        "takvim_degisti":   takvim_degisti,
        "diger_uretimler":  diger_uretimler,
        "is_superuser":     request.user.is_superuser,
        "is_staff":         request.user.is_staff or request.user.is_superuser,
    })


@require_POST
def calistir_oturma_secili(request):
    """Seçili oturumlar için oturma planı oluştur (arka plan görevi)."""
    import json as _json
    try:
        sessions = _json.loads(request.body).get("sessions", [])
    except Exception:
        sessions = []
    if not sessions:
        return JsonResponse({"error": "En az bir oturum seçin."}, status=400)

    # Bayrağı sıfırla
    aktif = _aktif_sinav()
    if aktif:
        from sinav.models import TakvimUretim as _TU
        _TU.objects.filter(sinav=aktif, aktif=True).update(oturma_sifirla=False, degisiklik_logu="")

    task_id = _new_task()
    session_cfg = dict(request.session.get("ortaksinav_config", {}))
    t = threading.Thread(
        target=_run_oturma_secili,
        args=(task_id, session_cfg, sessions),
        daemon=True,
    )
    t.start()
    return JsonResponse({"task_id": task_id})


def _run_oturma_secili(task_id: str, session_cfg: dict, sessions: list):
    try:
        config_uygula(session_cfg)
        from ortaksinav_engine.services.oturma import OturmaPlanService
        OturmaPlanService(CONFIG, log_fn=lambda m: _log(task_id, m)).generate_selected(sessions)
        if _TASKS.get(task_id, {}).get("cancel"):
            _finish(task_id, error=True)
            return
    except Exception as e:
        _log(task_id, f"! Hata: {e}")
        _log(task_id, traceback.format_exc())
        _finish(task_id, error=True)
        return
    _finish(task_id)


@login_required
def oturma_plani_pdf_view(request):
    """OturmaPlani DB'den Oturma Planı PDF'ini anlık üretip döner."""
    import io
    import re as _re
    from datetime import datetime as _dt

    from ortaksinav_engine.services.pdf_rapor import oturum_plani_pdf
    from sinav.models import OturmaPlani, OturmaUretim

    tarih_str  = request.GET.get("tarih", "")
    saat       = request.GET.get("saat", "")
    oturum     = int(request.GET.get("oturum", 1))
    uretim_pk  = request.GET.get("uretim")
    try:
        tarih_date = _dt.strptime(tarih_str, "%Y-%m-%d").date()
    except ValueError:
        raise Http404

    # OturmaUretim üzerinden doğru TakvimUretim'i bul
    if uretim_pk:
        ou = OturmaUretim.objects.filter(
            takvim_uretim_id=int(uretim_pk), tarih=tarih_date, saat=saat, oturum=oturum
        ).select_related("takvim_uretim").first()
        if not ou:
            # Aktif TakvimUretim değişmiş olabilir; planı üreten gerçek kaydı bul
            ou = OturmaUretim.objects.filter(
                tarih=tarih_date, saat=saat, oturum=oturum
            ).select_related("takvim_uretim").first()
        if not ou:
            raise Http404
        aktif_uretim = ou.takvim_uretim
    else:
        from sinav.models import TakvimUretim as _TU
        aktif_uretim = _TU.objects.filter(sinav=_aktif_sinav(), aktif=True).first()

    salon_filter = request.GET.get("salon", "")
    qs = OturmaPlani.objects.filter(
        tarih=tarih_date, saat=saat, oturum=oturum, uretim=aktif_uretim
    )
    if salon_filter:
        qs = qs.filter(salon=salon_filter)
    qs = qs.order_by("salon", "sira_no")
    if not qs.exists():
        raise Http404

    salon_grids = {}
    for op in qs:
        if op.salon not in salon_grids:
            salon_grids[op.salon] = [[[None] * 2 for _ in range(6)] for _ in range(3)]
        sira  = op.sira_no - 1
        block = sira // 12
        rem   = sira % 12
        row   = rem // 2
        col   = rem % 2
        if block < 3 and row < 6 and col < 2:
            sinifsube = str(op.sinifsube or "")
            m = _re.search(r"(\d+)", sinifsube)
            parts = (op.adi_soyadi or "").split(" ", 1)
            salon_grids[op.salon][block][row][col] = {
                "okulno":    op.okulno,
                "sinifsube": sinifsube,
                "adi":       parts[0] if parts else "",
                "soyadi":    parts[1] if len(parts) > 1 else "",
                "ders":      op.ders_adi or "",
                "sinif":     m.group(1) if m else "",
            }

    baslik = f"{tarih_str} {saat} (Oturum {oturum})"
    okul   = OkulBilgi.get()
    buf    = io.BytesIO()
    oturum_plani_pdf(salon_grids, buf, baslik, okul, aktif_uretim, tarih=tarih_date, saat=saat)
    buf.seek(0)
    fname = f"Oturma_Plani_{tarih_str}_{saat.replace(':', '')}.pdf"
    return HttpResponse(buf.read(), content_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})


@login_required
def sinav_takvimi_pdf_view(request):
    """Aktif TakvimUretim'e bağlı tek sayfalık öğrenci Sınav Takvimi PDF'i döner.
    ?subeler=0  →  Şubeler sütunu olmadan üretir (varsayılan: şubeli).
    """
    import io

    from ortaksinav_engine.services.pdf_rapor import sinav_takvimi_pdf
    from sinav.models import TakvimUretim

    aktif = _aktif_sinav()
    if not aktif:
        raise Http404

    aktif_uretim = TakvimUretim.objects.filter(sinav=aktif, aktif=True).first()
    if not aktif_uretim:
        raise Http404

    from sinav.models import Takvim as TakvimModel
    TakvimModel.objects.filter(sinav=aktif, uretim__isnull=True).update(uretim=aktif_uretim)

    goster_subeler = request.GET.get("subeler", "1") != "0"
    okul = OkulBilgi.get()
    buf  = io.BytesIO()
    sinav_takvimi_pdf(buf, okul, aktif_uretim,
                      hazirlayan_user=request.user,
                      goster_subeler=goster_subeler)
    buf.seek(0)
    etiket = "" if goster_subeler else "_subesiz"
    fname = f"Sinav_Takvimi{etiket}_{aktif.egitim_ogretim_yili}.pdf"
    return HttpResponse(buf.read(), content_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})


@login_required
def sinav_takvimi_subesiz_pdf_view(request):
    """Şubeler sütunu olmadan sınav takvimi PDF'i döner."""
    import io

    from ortaksinav_engine.services.pdf_rapor import sinav_takvimi_pdf
    from sinav.models import TakvimUretim

    aktif = _aktif_sinav()
    if not aktif:
        raise Http404

    aktif_uretim = TakvimUretim.objects.filter(sinav=aktif, aktif=True).first()
    if not aktif_uretim:
        raise Http404

    from sinav.models import Takvim as TakvimModel
    TakvimModel.objects.filter(sinav=aktif, uretim__isnull=True).update(uretim=aktif_uretim)

    okul = OkulBilgi.get()
    buf  = io.BytesIO()
    sinav_takvimi_pdf(buf, okul, aktif_uretim,
                      hazirlayan_user=request.user,
                      goster_subeler=False)
    buf.seek(0)
    fname = f"Sinav_Takvimi_subesiz_{aktif.egitim_ogretim_yili}.pdf"
    return HttpResponse(buf.read(), content_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})


@login_required
def sinif_listesi_pdf_view(request):
    """OturmaPlani DB'den Sınıf Listesi PDF'ini anlık üretip döner."""
    import io
    from datetime import datetime as _dt

    from ortaksinav_engine.services.pdf_rapor import sinif_raporu_pdf
    from sinav.models import OturmaPlani, OturmaUretim

    tarih_str      = request.GET.get("tarih", "")
    saat           = request.GET.get("saat", "")
    oturum         = int(request.GET.get("oturum", 1))
    uretim_pk      = request.GET.get("uretim")
    sinifsube_filtre = request.GET.get("sinifsube", "") or None
    try:
        tarih_date = _dt.strptime(tarih_str, "%Y-%m-%d").date()
    except ValueError:
        raise Http404

    # OturmaUretim üzerinden doğru TakvimUretim'i bul
    if uretim_pk:
        ou = OturmaUretim.objects.filter(
            takvim_uretim_id=int(uretim_pk), tarih=tarih_date, saat=saat, oturum=oturum
        ).select_related("takvim_uretim").first()
        if not ou:
            # Aktif TakvimUretim değişmiş olabilir; planı üreten gerçek kaydı bul
            ou = OturmaUretim.objects.filter(
                tarih=tarih_date, saat=saat, oturum=oturum
            ).select_related("takvim_uretim").first()
        if not ou:
            raise Http404
        aktif_uretim = ou.takvim_uretim
    else:
        from sinav.models import TakvimUretim as _TU2
        aktif_uretim = _TU2.objects.filter(sinav=_aktif_sinav(), aktif=True).first()
        if not OturmaPlani.objects.filter(
            tarih=tarih_date, saat=saat, oturum=oturum, uretim=aktif_uretim
        ).exists():
            raise Http404

    okul  = OkulBilgi.get()
    buf   = io.BytesIO()
    sinif_raporu_pdf(tarih_date, saat, oturum, buf, okul, aktif_uretim, sinifsube_filter=sinifsube_filtre)
    buf.seek(0)
    fname = f"Sinif_Listesi_{tarih_str}_{saat.replace(':', '')}.pdf"
    return HttpResponse(buf.read(), content_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})


@require_POST
@login_required
def takvim_uretim_aciklama_guncelle(request, pk):
    import json

    from django.http import JsonResponse

    from sinav.models import TakvimUretim
    uretim = TakvimUretim.objects.filter(pk=pk).first()
    if not uretim:
        return JsonResponse({"ok": False}, status=404)
    try:
        data = json.loads(request.body)
    except (ValueError, KeyError):
        return JsonResponse({"ok": False}, status=400)
    uretim.aciklama = data.get("aciklama", "").strip()[:200]
    uretim.save(update_fields=["aciklama"])
    return JsonResponse({"ok": True, "aciklama": uretim.aciklama})


@require_POST
def takvim_uretim_sil(request, pk):
    from sinav.models import TakvimUretim
    TakvimUretim.objects.filter(pk=pk).delete()
    return redirect("sinav:takvim_gecmisi")


@require_POST
def takvim_uretim_kullan(request, pk):
    from sinav.models import TakvimUretim
    uretim = TakvimUretim.objects.filter(pk=pk).select_related("sinav").first()
    if uretim:
        # Aynı sınava ait tüm üretimleri pasif yap, sonra seçileni aktif et
        TakvimUretim.objects.filter(sinav=uretim.sinav).update(aktif=False)
        uretim.aktif = True
        uretim.save(update_fields=["aktif"])
        from django.utils import timezone as _tz
        messages.success(request, f"PDF rapor için takvim seçildi: {_tz.localtime(uretim.uretim_tarihi):%d.%m.%Y %H:%M}")
    else:
        messages.error(request, "Kayıt bulunamadı.")
    return redirect("sinav:takvim_gecmisi")


# ---------------------------------------------------------------
# Gorev baslatici (arka plan thread)
# ---------------------------------------------------------------
ADIM_FUNCLARI = {
    "temel_veriler":  (temel_verileri_olustur,    "Temel Veriler (DersHavuzu + SinifSube)"),
    "veri_aktar":     (verileri_aktar,            "Veri Aktarimi (DersProgram + Ogrenci)"),
    "subeders":       (subeders_guncelle,          "SubeDers Guncelle"),
    "takvim":         (takvim_olustur,             "Sinav Takvimi (ILP)"),
    "oturma":         (oturma_planlarini_olustur,  "Oturma Planlari"),
}


def _run_step(task_id: str, session_cfg: dict, func_name: str):
    _, label = ADIM_FUNCLARI[func_name]
    try:
        config_uygula(session_cfg)
        _log(task_id, f"> {label} baslatildi...")

        if func_name == "takvim":
            from ortaksinav_engine.services.takvim import TakvimService

            def _cancel_fn():
                with _TASKS_LOCK:
                    return _TASKS.get(task_id, {}).get("cancel", False)

            svc = TakvimService(CONFIG, log_fn=lambda m: _log(task_id, m), cancel_fn=_cancel_fn)
            svc.takvimolustur()
        else:
            func, _ = ADIM_FUNCLARI[func_name]
            func()

        if _TASKS.get(task_id, {}).get("cancel"):
            _finish(task_id, error=True)
            return
        _log(task_id, f"+ {label} tamamlandi.")
    except Exception as e:
        _log(task_id, f"! Hata: {e}")
        _log(task_id, traceback.format_exc())
        _finish(task_id, error=True)
        return

    if func_name == "takvim":
        try:
            from sinav.models import SinavBilgisi as _SB
            from sinav.models import TakvimUretim
            aktif = _SB.objects.filter(aktif=True).first()
            if aktif:
                log_text = "\n".join(_TASKS.get(task_id, {}).get("logs", []))
                TakvimUretim.objects.create(
                    sinav=aktif,
                    log_metni=log_text,
                    onizleme_verisi=getattr(svc, "_onizleme_kayitlar", None),
                )
        except Exception:
            pass

    _finish(task_id)


def _start_task(request, func_name: str) -> JsonResponse:
    task_id = _new_task()
    session_cfg = dict(request.session.get("ortaksinav_config", {}))
    t = threading.Thread(
        target=_run_step, args=(task_id, session_cfg, func_name), daemon=True
    )
    t.start()
    return JsonResponse({"task_id": task_id})


@require_POST
def calistir_temel_veriler(request):
    return _start_task(request, "temel_veriler")

@require_POST
def calistir_veri_aktar(request):
    return _start_task(request, "veri_aktar")

@require_POST
def calistir_subeders(request):
    return _start_task(request, "subeders")

@require_POST
def calistir_takvim(request):
    return _start_task(request, "takvim")

@require_POST
def calistir_oturma(request):
    return _start_task(request, "oturma")


# ---------------------------------------------------------------
# Gorev durumu (polling) + iptal
# ---------------------------------------------------------------
@login_required
def gorev_durumu(request, task_id: str):
    with _TASKS_LOCK:
        task = _TASKS.get(task_id)
    if task is None:
        return JsonResponse({"error": "Gorev bulunamadi"}, status=404)
    return JsonResponse({
        "logs": task["logs"],
        "done": task["done"],
        "error": task["error"],
    })


@require_POST
def gorev_iptal(request, task_id: str):
    with _TASKS_LOCK:
        if task_id in _TASKS and not _TASKS[task_id]["done"]:
            _TASKS[task_id]["cancel"] = True
            _TASKS[task_id]["logs"].append(
                "! Durdurma istegi alindi. Mevcut ILP adimlari tamamlaninca durulacak..."
            )
    return JsonResponse({"ok": True})



# ---------------------------------------------------------------
# Sinav Bilgisi CRUD
# ---------------------------------------------------------------
@login_required
def sinav_bilgisi_listesi(request):
    okul = OkulBilgi.get()
    okul_tamam = bool(okul.okul_adi.strip())

    kurulum = _kurulum_durumu()

    if request.method == "POST":
        if not okul_tamam:
            messages.error(request, "Önce Okul Bilgilerini doldurun.")
            return redirect("sinav:sinav_bilgisi_listesi")
        if not kurulum["veri_tamam"]:
            messages.error(request, "Sınav oluşturmadan önce e-Okul verilerini (öğrenci ve ders programı) yükleyin.")
            return redirect("sinav:sinav_bilgisi_listesi")
        form = SinavBilgisiForm(request.POST)
        if form.is_valid():
            sinav = form.save(commit=False)
            sinav.kurum = okul
            sinav.save()
            messages.success(request, "Sınav bilgisi oluşturuldu.")
            return redirect("sinav:sinav_bilgisi_listesi")
    else:
        form = SinavBilgisiForm()

    liste = SinavBilgisi.objects.all()
    dosya = _dosya_durumu(request)
    aktif_sinav = _aktif_sinav()
    mazeret_sayisi = MazeretSinav.objects.filter(sinav=aktif_sinav).count() if aktif_sinav else 0

    return render(request, "sinav/sinav_bilgisi.html", {
        "form":           form,
        "liste":          liste,
        "aktif_sinav":    aktif_sinav,
        "okul":           okul,
        "okul_tamam":     okul_tamam,
        "db_ozeti":       db_ozeti(),
        "mazeret_sayisi": mazeret_sayisi,
        **kurulum,
        **dosya,
    })


@require_POST
def okul_bilgileri_kaydet(request):
    """Okul bilgileri artık /okul-ayarlari/ sayfasından yönetilmektedir."""
    return redirect("main:okul_ayarlari")


@require_POST
def sinav_bilgisi_duzenle(request, pk: int):
    obj = SinavBilgisi.objects.get(pk=pk)
    form = SinavBilgisiForm(request.POST, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, "Sınav bilgisi güncellendi.")
    else:
        for field in form:
            for err in field.errors:
                messages.error(request, f"{field.label}: {err}")
    return redirect("sinav:sinav_bilgisi_listesi")


@require_POST
def sinav_bilgisi_sil(request, pk: int):
    obj = SinavBilgisi.objects.get(pk=pk)
    obj.delete()
    messages.success(request, "Sınav bilgisi silindi.")
    return redirect("sinav:sinav_bilgisi_listesi")


# ---------------------------------------------------------------
# Ogrenci Yonetimi
# ---------------------------------------------------------------
@login_required
def ogrenci_yonetim(request):
    aktif = _aktif_sinav()
    arama = request.GET.get("q", "").strip()
    sinif_filtre = request.GET.get("sinif", "").strip()
    from django.db.models import Q
    qs = OgrenciModel.objects.all()
    if arama:
        qs = qs.filter(
            Q(adi__icontains=arama) | Q(soyadi__icontains=arama) | Q(okulno__icontains=arama)
        )
    if sinif_filtre:
        qs = qs.filter(sinif=sinif_filtre)
    siniflar = OgrenciModel.objects.values_list("sinif", flat=True).distinct().order_by("sinif")
    return render(request, "sinav/ogrenci_yonetim.html", {
        "ogrenciler":   qs[:200],
        "arama":        arama,
        "sinif_filtre": sinif_filtre,
        "siniflar":     siniflar,
        "toplam":       qs.count(),
        "aktif_sinav":  aktif,
    })


@require_POST
def ogrenci_ekle(request):
    """Öğrenci yönetimi Veri Aktarım sayfasından yapılmaktadır."""
    messages.info(request, "Öğrenci eklemek için Veri Aktarım sayfasını kullanın.")
    return redirect("sinav:ogrenci_yonetim")


@require_POST
def ogrenci_sil(request, pk: int):
    try:
        ogr = OgrenciModel.objects.get(pk=pk)
        ad = f"{ogr.adi} {ogr.soyadi} ({ogr.sinifsube})"
        ogr.delete()
        messages.success(request, f"{ad} listeden çıkarıldı.")
    except OgrenciModel.DoesNotExist:
        messages.error(request, "Öğrenci bulunamadı.")
    return redirect("sinav:ogrenci_yonetim")


# ---------------------------------------------------------------
# Ders Ayarlari
# ---------------------------------------------------------------
_VARSAYILAN_SINAV_YAPILMAYACAK = [
    "GÖRSEL SANATLAR/MÜZİK",
    "BEDEN EĞİTİMİ VE SPOR/GÖRSEL SANATLAR/MÜZİK",
    "BEDEN EĞİTİMİ VE SPOR",
    "SEÇMELİ SANAT EĞİTİMİ",
    "REHBERLİK VE YÖNLENDİRME",
    "SEÇMELİ SPOR EĞİTİMİ",
    "SEÇMELİ HEDEF TEMELLİ DESTEK EĞİTİMİ",
    "SEÇMELİ YABANCI DİL",
]

_VARSAYILAN_CIFT_OTURUMLU = [
    "SEÇMELİ İKİNCİ YABANCI DİL",
    "SEÇMELİ TÜRK DİLİ VE EDEBİYATI",
    "TÜRK DİLİ VE EDEBİYATI",
    "YABANCI DİL",
]


def _bolumle(tum_dersler: list, efektif: set) -> tuple[list, list]:
    """Dersleri iki gruba ayirir: efektif secili (uste) ve diger (alta)."""
    secili = sorted(d for d in tum_dersler if d in efektif)
    diger  = sorted(d for d in tum_dersler if d not in efektif)
    return secili, diger


@login_required
def ders_ayarlari(request):
    from okul.models import DersHavuzu
    aktif = _aktif_sinav()
    veri = _get_ayarlar(aktif)

    dp_dersler = list(DersHavuzu.objects.order_by("ders_adi"))
    tum_dersler = sorted(DersHavuzu.objects.values_list("ders_adi", flat=True))

    catisma_gruplari      = veri.get("catisma_gruplari", [])
    esleme_ciftleri       = veri.get("ayni_slot_esleme", [])
    sabit_raw             = veri.get("sabit_sinavlar", [])
    ortak_sinav_seviyeleri = veri.get("ortak_sinav_seviyeleri", [9, 10, 11, 12])

    import json as _json
    varsayilan_catisma = {
        "grup_adi": _VARSAYILAN_CATISMA_GRUBU["grup_adi"],
        "dersler": [d.strip() for d in _VARSAYILAN_CATISMA_GRUBU["dersler"].split(",") if d.strip()],
    }

    yapilmayacak_dersler = [d for d in dp_dersler if d.sinav_yapilmayacak]
    cift_dersler         = [d for d in dp_dersler if d.cift_oturum == 1]

    return render(request, "sinav/ders_ayarlari.html", {
        "aktif_sinav":          aktif,
        "dp_dolu":              bool(dp_dersler),
        # DB'den okunan listeler (salt okunur gösterim)
        "yapilmayacak_dersler": yapilmayacak_dersler,
        "cift_dersler":         cift_dersler,
        # JS icin JSON dizgileri
        "sabit_json":              _json.dumps(sabit_raw, ensure_ascii=False),
        "catisma_json":            _json.dumps(catisma_gruplari, ensure_ascii=False),
        "esleme_json":             _json.dumps(esleme_ciftleri, ensure_ascii=False),
        "varsayilan_catisma_json": _json.dumps(varsayilan_catisma, ensure_ascii=False),
        "tum_dersler_sabit":       tum_dersler,
        "ortak_sinav_seviyeleri":  ortak_sinav_seviyeleri,
    })


@require_POST
def ders_ayarlari_kaydet(request):
    aktif = _aktif_sinav()
    if not aktif:
        messages.error(request, "Önce aktif bir sınav seçin.")
        return redirect("sinav:ders_ayarlari")

    import json as _json
    veri = _get_ayarlar(aktif)

    for key, field in [("sabit_sinavlar", "sabit_json"),
                        ("catisma_gruplari", "catisma_json"),
                        ("ayni_slot_esleme", "esleme_json")]:
        raw = request.POST.get(field, "").strip()
        if raw:
            try:
                veri[key] = _json.loads(raw)
            except Exception:
                pass

    raw_seviyeler = request.POST.get("ortak_seviyeler_json", "").strip()
    if raw_seviyeler:
        try:
            parsed = _json.loads(raw_seviyeler)
            seviyelar = sorted({int(s) for s in parsed if str(s).isdigit() or isinstance(s, int)})
            if seviyelar:
                veri["ortak_sinav_seviyeleri"] = seviyelar
        except Exception:
            pass

    _save_ayarlar(aktif, veri)

    # Otomatik: SubeDers yenile
    session_cfg = dict(request.session.get("ortaksinav_config", {}))
    config_uygula(session_cfg)
    try:
        from ortaksinav_engine.services.ders_analiz import DersAnalizService
        DersAnalizService(CONFIG).subeders_guncelle(aktif)
        from sinav.models import SubeDers
        n = SubeDers.objects.count()
        from okul.models import DersHavuzu as _DH
        n_yap  = _DH.objects.filter(sinav_yapilmayacak=True).count()
        n_cift = _DH.objects.filter(cift_oturum=1).count()
        messages.success(
            request,
            f"Ders ayarları kaydedildi ve dersler filtrelendi "
            f"({n_yap} hariç, {n_cift} çift oturumlu, {n} aktif ders/şube)."
        )
    except Exception as e:
        messages.error(request, f"Ders filtreleme hatası: {e}")
    return redirect("sinav:ders_ayarlari")


@require_POST
def ders_ayarlari_varsayilan_yukle(request):
    aktif = _aktif_sinav()
    if not aktif:
        messages.error(request, "Önce aktif bir sınav seçin.")
        return redirect("sinav:ders_ayarlari")
    tip = request.POST.get("tip", "")
    veri = _get_ayarlar(aktif)
    if tip == "yapilmayacak":
        mevcut = set(veri.get("yapilmayacak", []))
        veri["yapilmayacak"] = sorted(mevcut | set(_VARSAYILAN_SINAV_YAPILMAYACAK))
        _save_ayarlar(aktif, veri)
        messages.success(request, "Varsayılan 'sınav yapılmayacak' listesi yüklendi.")
    elif tip == "cift":
        mevcut = set(veri.get("cift_oturumlu", []))
        veri["cift_oturumlu"] = sorted(mevcut | set(_VARSAYILAN_CIFT_OTURUMLU))
        _save_ayarlar(aktif, veri)
        messages.success(request, "Varsayılan 'iki oturumlu' listesi yüklendi.")
    return redirect("sinav:ders_ayarlari")


# ---------------------------------------------------------------
# Sabit Sinavlar (tarihi/saati onceden belirlenmis ortak sinavlar)
# ---------------------------------------------------------------
@require_POST
def sabit_sinav_ekle(request):
    aktif = _aktif_sinav()
    if not aktif:
        messages.error(request, "Önce aktif bir sınav seçin.")
        return redirect("sinav:ders_ayarlari")
    ders_adi  = request.POST.get("ders_adi", "").strip()
    tarih     = request.POST.get("tarih", "").strip()
    saat      = request.POST.get("saat", "").strip()
    seviyeler = [int(s) for s in sorted(set(request.POST.getlist("seviye"))) if s.isdigit()]
    if not ders_adi or not tarih or not saat:
        messages.error(request, "Ders adı, tarih ve saat zorunludur.")
        return redirect("sinav:ders_ayarlari")
    veri = _get_ayarlar(aktif)
    liste = veri.get("sabit_sinavlar", [])
    yeni = {"ders_adi": ders_adi, "tarih": tarih, "saat": saat, "seviyeler": seviyeler}
    guncellendi = False
    for i, ss in enumerate(liste):
        if ss["ders_adi"] == ders_adi:
            liste[i] = yeni
            guncellendi = True
            break
    if not guncellendi:
        liste.append(yeni)
    veri["sabit_sinavlar"] = liste
    _save_ayarlar(aktif, veri)
    if guncellendi:
        messages.success(request, f'"{ders_adi}" sabit sınav güncellendi.')
    else:
        messages.success(request, f'"{ders_adi}" sabit sınav olarak eklendi.')
    return redirect("sinav:ders_ayarlari")


@require_POST
def sabit_sinav_sil(request, idx: int):
    aktif = _aktif_sinav()
    veri = _get_ayarlar(aktif)
    liste = veri.get("sabit_sinavlar", [])
    if 0 <= idx < len(liste):
        ad = liste[idx]["ders_adi"]
        liste.pop(idx)
        veri["sabit_sinavlar"] = liste
        _save_ayarlar(aktif, veri)
        messages.success(request, f'"{ad}" sabit sınavdan çıkarıldı.')
    else:
        messages.error(request, "Kayıt bulunamadı.")
    return redirect("sinav:ders_ayarlari")


# ---------------------------------------------------------------
# Seviye Çakışma Grupları
# ---------------------------------------------------------------
_VARSAYILAN_CATISMA_GRUBU = {
    "grup_adi": "Fen-Matematik Grubu",
    "dersler":  "BİYOLOJİ,FİZİK,KİMYA,MATEMATİK,"
                "SEÇMELİ BİYOLOJİ,SEÇMELİ FİZİK,SEÇMELİ KİMYA,SEÇMELİ MATEMATİK",
}


@require_POST
def catisma_grubu_ekle(request):
    aktif = _aktif_sinav()
    if not aktif:
        messages.error(request, "Önce aktif bir sınav seçin.")
        return redirect("sinav:ders_ayarlari")
    grup_adi = request.POST.get("grup_adi", "").strip()
    dersler  = request.POST.get("dersler", "").strip()
    if not grup_adi or not dersler:
        messages.error(request, "Grup adı ve en az bir ders zorunludur.")
        return redirect("sinav:ders_ayarlari")
    ders_listesi = [d.strip() for d in dersler.replace("\n", ",").split(",") if d.strip()]
    veri = _get_ayarlar(aktif)
    liste = veri.get("catisma_gruplari", [])
    liste.append({"grup_adi": grup_adi, "dersler": ders_listesi})
    veri["catisma_gruplari"] = liste
    _save_ayarlar(aktif, veri)
    messages.success(request, f'"{grup_adi}" çakışma grubu eklendi ({len(ders_listesi)} ders).')
    return redirect("sinav:ders_ayarlari")


@require_POST
def catisma_grubu_sil(request, idx: int):
    aktif = _aktif_sinav()
    veri = _get_ayarlar(aktif)
    liste = veri.get("catisma_gruplari", [])
    if 0 <= idx < len(liste):
        ad = liste[idx]["grup_adi"]
        liste.pop(idx)
        veri["catisma_gruplari"] = liste
        _save_ayarlar(aktif, veri)
        messages.success(request, f'"{ad}" çakışma grubu silindi.')
    else:
        messages.error(request, "Kayıt bulunamadı.")
    return redirect("sinav:ders_ayarlari")


@require_POST
def catisma_grubu_varsayilan(request):
    aktif = _aktif_sinav()
    if not aktif:
        messages.error(request, "Önce aktif bir sınav seçin.")
        return redirect("sinav:ders_ayarlari")
    ders_listesi = [d.strip() for d in _VARSAYILAN_CATISMA_GRUBU["dersler"].split(",") if d.strip()]
    veri = _get_ayarlar(aktif)
    liste = veri.get("catisma_gruplari", [])
    liste.append({"grup_adi": _VARSAYILAN_CATISMA_GRUBU["grup_adi"], "dersler": ders_listesi})
    veri["catisma_gruplari"] = liste
    _save_ayarlar(aktif, veri)
    messages.success(request, "Varsayılan çakışma grubu eklendi.")
    return redirect("sinav:ders_ayarlari")


@require_POST
def esleme_ekle(request):
    aktif = _aktif_sinav()
    if not aktif:
        messages.error(request, "Önce aktif bir sınav seçin.")
        return redirect("sinav:ders_ayarlari")
    ders1 = request.POST.get("ders1", "").strip().upper()
    ders2 = request.POST.get("ders2", "").strip().upper()
    if not ders1 or not ders2:
        messages.error(request, "Her iki ders adı da zorunludur.")
        return redirect("sinav:ders_ayarlari")
    if ders1 == ders2:
        messages.error(request, "İki ders farklı olmalıdır.")
        return redirect("sinav:ders_ayarlari")
    veri = _get_ayarlar(aktif)
    liste = veri.get("ayni_slot_esleme", [])
    if any(e["ders1"] == ders1 and e["ders2"] == ders2 for e in liste):
        messages.info(request, "Bu eşleme zaten kayıtlı.")
    else:
        liste.append({"ders1": ders1, "ders2": ders2})
        veri["ayni_slot_esleme"] = liste
        _save_ayarlar(aktif, veri)
        messages.success(request, f'"{ders1}" ↔ "{ders2}" eşlemesi eklendi.')
    return redirect("sinav:ders_ayarlari")


@require_POST
def esleme_sil(request, idx: int):
    aktif = _aktif_sinav()
    veri = _get_ayarlar(aktif)
    liste = veri.get("ayni_slot_esleme", [])
    if 0 <= idx < len(liste):
        liste.pop(idx)
        veri["ayni_slot_esleme"] = liste
        _save_ayarlar(aktif, veri)
        messages.success(request, "Eşleme silindi.")
    else:
        messages.error(request, "Kayıt bulunamadı.")
    return redirect("sinav:ders_ayarlari")


# ---------------------------------------------------------------
# Öğrenci Sınav Yeri Sorgulama
# ---------------------------------------------------------------
def _sinav_sorgu_izni(user):
    """mudur_yardimcisi, okul_muduru, ogretmen ve benzeri tüm okul personeline izin verir."""
    if user.is_superuser or user.is_staff:
        return True
    gruplar = set(user.groups.values_list("name", flat=True))
    return bool(gruplar & {
        "mudur_yardimcisi", "okul_muduru",
        "ogretmen", "rehber_ogretmen", "disiplin_kurulu",
    })


@login_required
def ogrenci_sinav_yeri(request):
    if not _sinav_sorgu_izni(request.user):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    okulno   = request.GET.get("okulno", "").strip()
    sonuclar = []
    hata     = None

    bugun        = date.today()
    gosterim_tarihi = None

    if okulno:
        if not aktif_uretim:
            hata = "Aktif sınav takvimi bulunamadı."
        else:
            tum_sonuclar = list(
                OturmaPlani.objects
                .filter(uretim=aktif_uretim, okulno=okulno)
                .order_by("tarih", "saat", "oturum")
                .values("tarih", "saat", "salon", "sira_no", "ders_adi", "sinifsube", "adi_soyadi")
            )
            if not tum_sonuclar:
                hata = f"'{okulno}' okul numarasına ait kayıt bulunamadı."
            else:
                # Bugünkü oturumlar varsa onları, yoksa en yakın gelecek tarihi göster
                bugun_sonuclar = [s for s in tum_sonuclar if s["tarih"] == bugun]
                if bugun_sonuclar:
                    sonuclar        = bugun_sonuclar
                    gosterim_tarihi = bugun
                else:
                    yakin_tarih = next(
                        (s["tarih"] for s in tum_sonuclar if s["tarih"] > bugun), None
                    )
                    if yakin_tarih:
                        sonuclar        = [s for s in tum_sonuclar if s["tarih"] == yakin_tarih]
                        gosterim_tarihi = yakin_tarih
                    else:
                        # Tüm sınavlar geçmiş
                        hata = "Yaklaşan sınav oturumu bulunmuyor (tüm oturumlar geçmiş)."

    return render(request, "sinav/ogrenci_sinav_yeri.html", {
        "aktif_sinav":      aktif_sinav,
        "aktif_uretim":     aktif_uretim,
        "okulno":           okulno,
        "sonuclar":         sonuclar,
        "hata":             hata,
        "bugun":            bugun,
        "gosterim_tarihi":  gosterim_tarihi,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Sınav Yoklama Raporu — Yönetim
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def sinav_yoklama_raporu(request):
    """Seviye ve Ders filtreli sınav yoklama listesi — yöneticiler için."""
    from django.core.exceptions import PermissionDenied

    from okul.auth import is_ust_yonetici

    if not is_ust_yonetici(request.user):
        raise PermissionDenied

    from django.db.models import Q

    from sinav.models import OturmaPlani, SinavSalonYoklama, Takvim, TakvimUretim

    aktif_sinav  = _aktif_sinav()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    # ── Filtre seçenekleri: Takvim FK üzerinden ders ID + adı ────────────────
    dersler = []
    if aktif_uretim:
        dersler = list(
            Takvim.objects
            .filter(uretim=aktif_uretim, ders__isnull=False)
            .select_related("ders")
            .values("ders_id", "ders__ders_adi")
            .distinct()
            .order_by("ders__ders_adi")
        )  # [{"ders_id": 3, "ders__ders_adi": "Matematik"}, ...]

    SEVIYELER = [9, 10, 11, 12]

    # ── Filtre değerleri ─────────────────────────────────────────────────────
    filtre_seviye  = request.GET.get("seviye", "").strip()
    filtre_ders_id = request.GET.get("ders_id", "").strip()

    # ── Gruplama: (seviye, ders_adi, tarih) bazında salon bağımsız istatistik ──
    satirlar = []
    if aktif_uretim:
        from collections import defaultdict

        # Ders filtresi için DersHavuzu'ndan ders adı al
        filtre_ders_adi_base = None
        if filtre_ders_id:
            from okul.models import DersHavuzu as _DH
            _ders_obj = _DH.objects.filter(pk=filtre_ders_id).first()
            filtre_ders_adi_base = _ders_obj.ders_adi if _ders_obj else None
            if not filtre_ders_adi_base:
                # Havuzda ders yoksa boş sonuç döndür
                return render(request, "sinav/sinav_yoklama_raporu.html", {
                    "aktif_sinav": aktif_sinav, "aktif_uretim": aktif_uretim,
                    "dersler": dersler, "seviyeler": SEVIYELER,
                    "filtre_seviye": filtre_seviye, "filtre_ders_id": filtre_ders_id,
                    "satirlar": [],
                })

        # OturmaPlani filtrelemesi
        op_q = Q(uretim=aktif_uretim) & ~Q(ders_adi="")
        if filtre_seviye:
            op_q &= Q(sinifsube__startswith=f"{filtre_seviye}/")
        if filtre_ders_adi_base:
            op_q &= Q(ders_adi__istartswith=filtre_ders_adi_base)

        # (seviye, ders_adi, tarih) → okulno seti  (benzersiz öğrenci sayımı için)
        # (seviye, ders_adi, tarih) → set of (saat, salon)  (yoklama linkleri için)
        group_okulno: dict = defaultdict(set)
        group_salonlar: dict = defaultdict(set)
        for r in OturmaPlani.objects.filter(op_q).values(
            "sinifsube", "ders_adi", "tarih", "saat", "salon", "okulno"
        ):
            seviye = r["sinifsube"].split("/")[0] if "/" in r["sinifsube"] else r["sinifsube"]
            grp_key = (seviye, r["ders_adi"], r["tarih"])
            group_okulno[grp_key].add(r["okulno"])
            group_salonlar[grp_key].add((r["saat"], r["salon"]))

        # (tarih, okulno) → (seviye, ders_adi)  — yoklama eşleştirmesi için ters indeks
        okulno_to_group: dict = {}
        for (seviye, ders_adi, tarih), okulno_set in group_okulno.items():
            for okulno in okulno_set:
                okulno_to_group[(tarih, okulno)] = (seviye, ders_adi)

        # (seviye, ders_adi, tarih) → {durum: sayı}
        yoklama_ozet: dict = defaultdict(lambda: defaultdict(int))
        for y in SinavSalonYoklama.objects.filter(uretim=aktif_uretim).values("tarih", "okulno", "durum"):
            grp = okulno_to_group.get((y["tarih"], y["okulno"]))
            if grp:
                seviye, ders_adi = grp
                yoklama_ozet[(seviye, ders_adi, y["tarih"])][y["durum"]] += 1

        # Sonuç listesi
        for key in sorted(group_okulno.keys()):
            seviye, ders_adi, tarih = key
            toplam = len(group_okulno[key])
            yk     = yoklama_ozet.get(key, {})
            mevcut = yk.get("mevcut", 0)
            yok    = yk.get("yok", 0)
            gec    = yk.get("gec", 0)
            satirlar.append({
                "seviye":         seviye,
                "ders_adi":       ders_adi,
                "tarih":          tarih,
                "toplam":         toplam,
                "mevcut":         mevcut,
                "yok":            yok,
                "gec":            gec,
                "yoklama_alindi": bool(yk),
                "eksik":          toplam - (mevcut + yok + gec),
                "salonlar":       sorted(group_salonlar.get(key, [])),
            })

    # ── Öğrenci detay listesi: her iki filtre de seçiliyse ───────────────────
    ogrenci_listesi = []
    if aktif_uretim and filtre_seviye and filtre_ders_id and filtre_ders_adi_base:
        # Tüm öğrenciler (sinifsube, okulno, adi_soyadi)
        op_rows = list(
            OturmaPlani.objects
            .filter(
                uretim=aktif_uretim,
                sinifsube__startswith=f"{filtre_seviye}/",
                ders_adi__istartswith=filtre_ders_adi_base,
            )
            .values("sinifsube", "okulno", "adi_soyadi")
            .distinct()
            .order_by("sinifsube", "okulno")
        )
        # Yoklama durumları: okulno → durum
        yoklama_durumu = dict(
            SinavSalonYoklama.objects
            .filter(
                uretim=aktif_uretim,
            )
            .values_list("okulno", "durum")
        )
        for r in op_rows:
            durum = yoklama_durumu.get(r["okulno"], "")
            ogrenci_listesi.append({
                "sinifsube":  r["sinifsube"],
                "okulno":     r["okulno"],
                "adi_soyadi": r["adi_soyadi"],
                "durum":      durum,
            })

    return render(request, "sinav/sinav_yoklama_raporu.html", {
        "aktif_sinav":      aktif_sinav,
        "aktif_uretim":     aktif_uretim,
        "dersler":          dersler,
        "seviyeler":        SEVIYELER,
        "filtre_seviye":    filtre_seviye,
        "filtre_ders_id":   filtre_ders_id,
        "satirlar":         satirlar,
        "ogrenci_listesi":  ogrenci_listesi,
    })


def sinav_yoklama_yok_detay(request):
    """Belirli (seviye, ders_adi, tarih) için 'yok' durumundaki öğrencilerin listesi."""
    from collections import defaultdict

    from django.core.exceptions import PermissionDenied

    from okul.auth import is_ust_yonetici

    if not is_ust_yonetici(request.user):
        raise PermissionDenied

    from sinav.models import OturmaPlani, SinavSalonYoklama, TakvimUretim

    seviye   = request.GET.get("seviye", "").strip()
    ders_adi = request.GET.get("ders_adi", "").strip()
    tarih    = request.GET.get("tarih", "").strip()

    # "10 Nisan 2026" → datetime.date normalleştir
    _TR_AYLAR = {
        "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4,
        "mayıs": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
        "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
    }
    import datetime as _dt
    if tarih and not tarih[:4].isdigit():
        try:
            parcalar = tarih.split()
            gun, ay_str, yil = int(parcalar[0]), parcalar[1].lower(), int(parcalar[2])
            tarih = _dt.date(yil, _TR_AYLAR[ay_str], gun)
        except (ValueError, KeyError, IndexError):
            tarih = None

    aktif_sinav  = _aktif_sinav()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    gruplar_liste = []
    if aktif_uretim and seviye and ders_adi and tarih:
        # Seçili (seviye, ders_adi, tarih) için OturmaPlani okulno → satır bilgisi
        op_q = (
            OturmaPlani.objects
            .filter(
                uretim=aktif_uretim,
                sinifsube__startswith=f"{seviye}/",
                ders_adi=ders_adi,
                tarih=tarih,
            )
            .values("okulno", "adi_soyadi", "sinifsube")
            .distinct()
            .order_by("sinifsube", "okulno")
        )
        okulno_bilgi = {r["okulno"]: r for r in op_q}

        # Bu okulno'lar içinden "yok" olan yoklama kayıtları
        yok_okulnolar = set(
            SinavSalonYoklama.objects
            .filter(
                uretim=aktif_uretim,
                tarih=tarih,
                durum="yok",
                okulno__in=list(okulno_bilgi.keys()),
            )
            .values_list("okulno", flat=True)
            .distinct()
        )

        # Şube bazında grupla, okul no sıralı
        sube_map: dict = defaultdict(list)
        for okulno, bilgi in sorted(okulno_bilgi.items(),
                                    key=lambda x: (x[1]["sinifsube"], x[0])):
            if okulno in yok_okulnolar:
                sube_map[bilgi["sinifsube"]].append({
                    "okulno":    okulno,
                    "adi_soyadi": bilgi["adi_soyadi"],
                })

        gruplar_liste = [
            {"sinifsube": sube, "ogrenciler": ogrenciler}
            for sube, ogrenciler in sorted(sube_map.items())
        ]

    return render(request, "sinav/sinav_yoklama_yok_detay.html", {
        "aktif_sinav":   aktif_sinav,
        "seviye":        seviye,
        "ders_adi":      ders_adi,
        "tarih":         tarih,
        "gruplar":       gruplar_liste,
        "toplam_yok":    sum(len(g["ogrenciler"]) for g in gruplar_liste),
    })


# ===========================================================================
# Yoklama Simülasyonu
# ===========================================================================

@login_required
def mazeret_yoklama_simule(request):
    """
    Aktif takvim üretiminin OturmaPlani kayıtlarından SinavSalonYoklama
    simülasyonu oluşturur. Mazeret sınav planlamasını test etmek için kullanılır.

    Özel durum kuralları (mazeret ile aynı mantık):
    - Sürekli Devamsız (Ogrenci.sureksiz_devamsiz=True) → simülasyonda devamsız seçilmez
    - Muaf (OgrenciMuaf) → o ders için devamsız seçilmez
    """
    import random
    import re
    from collections import defaultdict

    from django.core.exceptions import PermissionDenied

    from ogrenci.models import Ogrenci as _Ogrenci
    from ogrenci.models import OgrenciMuaf as _OgrenciMuaf
    from okul.auth import is_ust_yonetici
    from okul.utils import get_aktif_egitim_yili

    if not is_ust_yonetici(request.user):
        raise PermissionDenied

    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    # ---------- Özel durum setleri (mazeret ile aynı) ----------
    _SINAV_TURU_RE = re.compile(r'^(.*?)\s+\((Yazili|Uygulama)\)$')

    def _base_ders(ders_adi_full: str) -> str:
        m = _SINAV_TURU_RE.match(ders_adi_full or "")
        return m.group(1).strip() if m else (ders_adi_full or "")

    sureksiz_okulnolari: set[str] = set(
        _Ogrenci.objects.filter(sureksiz_devamsiz=True).values_list("okulno", flat=True)
    )
    muaf_okulno_ders: set[tuple[str, str]] = set(
        _OgrenciMuaf.objects.filter(egitim_yili=get_aktif_egitim_yili())
        .values_list("ogrenci__okulno", "ders__ders_adi")
    )

    def _ozel_durum(okulno: str, ders_adi_full: str) -> str:
        """Özel durum varsa etiket döner; yoksa boş string."""
        if okulno in sureksiz_okulnolari:
            return "sureksiz"
        if (okulno, _base_ders(ders_adi_full)) in muaf_okulno_ders:
            return "muaf"
        return ""

    # ---------- Mevcut durum istatistikleri ----------
    toplam_oturum = 0
    toplam_ogrenci = 0
    toplam_haric = 0          # özel durumlu toplam
    yoklama_kayit_sayisi = 0
    yok_sayisi = 0
    oturum_listesi = []

    if aktif_uretim:
        # (tarih, saat, salon) → {ogrenci, haric} sayıları
        oturum_ozet: dict[tuple, dict] = defaultdict(lambda: {"ogrenci": 0, "haric": 0})
        for op in (
            OturmaPlani.objects
            .filter(uretim=aktif_uretim)
            .values("tarih", "saat", "salon", "okulno", "ders_adi")
            .order_by("tarih", "saat", "salon")
        ):
            key = (str(op["tarih"]), op["saat"], op["salon"])
            oturum_ozet[key]["ogrenci"] += 1
            if _ozel_durum(op["okulno"], op["ders_adi"]):
                oturum_ozet[key]["haric"] += 1

        # Yoklama durumu: oturum başına kayıt ve yok sayısı
        yoklama_ozet: dict[tuple, dict] = defaultdict(lambda: {"toplam": 0, "yok": 0})
        for yk in SinavSalonYoklama.objects.filter(uretim=aktif_uretim).values(
            "tarih", "saat", "salon", "durum"
        ):
            key = (str(yk["tarih"]), yk["saat"], yk["salon"])
            yoklama_ozet[key]["toplam"] += 1
            if yk["durum"] == "yok":
                yoklama_ozet[key]["yok"] += 1

        import datetime as _dt
        for key, oz in sorted(oturum_ozet.items()):
            tarih_str, saat_str, salon_str = key
            yk = yoklama_ozet.get(key, {"toplam": 0, "yok": 0})
            ogrenci = oz["ogrenci"]
            haric   = oz["haric"]
            try:
                tarih_obj = _dt.date.fromisoformat(tarih_str)
            except ValueError:
                tarih_obj = tarih_str
            oturum_listesi.append({
                "tarih":       tarih_obj,
                "saat":        saat_str,
                "salon":       salon_str,
                "ogrenci":     ogrenci,
                "haric":       haric,
                "uygun":       ogrenci - haric,
                "yoklama_var": yk["toplam"] > 0,
                "yok_sayisi":  yk["yok"],
            })
            toplam_oturum += 1
            toplam_ogrenci += ogrenci
            toplam_haric   += haric
            yoklama_kayit_sayisi += yk["toplam"]
            yok_sayisi += yk["yok"]

    # ---------- POST işlemleri ----------
    if request.method == "POST":
        action = request.POST.get("action", "simule")

        if action == "temizle":
            if aktif_uretim:
                silinen = SinavSalonYoklama.objects.filter(uretim=aktif_uretim).delete()
                messages.success(
                    request,
                    f"Aktif üretim için tüm yoklama kayıtları silindi ({silinen[0]} kayıt)."
                )
            else:
                messages.warning(request, "Aktif takvim üretimi bulunamadı.")
            return redirect("sinav:mazeret_yoklama_simule")

        if not aktif_uretim:
            messages.error(request, "Aktif takvim üretimi bulunamadı.")
            return redirect("sinav:mazeret_yoklama_simule")

        try:
            devamsizlik_yuzdesi = max(1, min(100, int(request.POST.get("devamsizlik_yuzdesi", 15))))
        except (ValueError, TypeError):
            devamsizlik_yuzdesi = 15

        mevcut_de_kaydet = request.POST.get("mevcut_de_kaydet") == "1"
        sifirla_once     = request.POST.get("sifirla_once") == "1"

        # Seçili oturumlar: "oturum_<tarih>_<saat>_<salon>" POST key'leri
        secili_keys = {
            k.removeprefix("oturum_")
            for k in request.POST
            if k.startswith("oturum_")
        }
        tumu_sec = not secili_keys

        from django.db.models import Q as _Q

        op_qs = OturmaPlani.objects.filter(uretim=aktif_uretim)
        if not tumu_sec:
            filtre = _Q()
            for key in secili_keys:
                parcalar = key.split("_", 2)
                if len(parcalar) == 3:
                    t_str, saat_str, salon_str = parcalar
                    filtre |= _Q(tarih=t_str, saat=saat_str, salon=salon_str)
            op_qs = op_qs.filter(filtre)

        kayitlar = list(
            op_qs.values(
                "tarih", "saat", "salon", "okulno",
                "adi_soyadi", "sinifsube", "sira_no", "ders_adi",
            ).order_by("tarih", "saat", "salon", "sira_no")
        )

        if sifirla_once:
            sil_qs = SinavSalonYoklama.objects.filter(uretim=aktif_uretim)
            if not tumu_sec:
                sil_filtre = _Q()
                for key in secili_keys:
                    parcalar = key.split("_", 2)
                    if len(parcalar) == 3:
                        t_str, saat_str, salon_str = parcalar
                        sil_filtre |= _Q(tarih=t_str, saat=saat_str, salon=salon_str)
                sil_qs = sil_qs.filter(sil_filtre)
            sil_qs.delete()

        # Simülasyon
        rng = random.Random()
        yeni_kayitlar = []
        yok_count = mevcut_count = haric_count = 0

        for r in kayitlar:
            ozel = _ozel_durum(r["okulno"], r["ders_adi"])

            if ozel:
                # Sürekli devamsız / muaf → sınava girmez; mevcut kaydı da oluşturma
                haric_count += 1
                continue

            is_absent = rng.random() * 100 < devamsizlik_yuzdesi
            if is_absent:
                durum = "yok"
                yok_count += 1
            elif mevcut_de_kaydet:
                durum = "mevcut"
                mevcut_count += 1
            else:
                continue

            yeni_kayitlar.append(SinavSalonYoklama(
                uretim=aktif_uretim,
                tarih=r["tarih"],
                saat=r["saat"],
                salon=r["salon"],
                okulno=r["okulno"],
                adi_soyadi=r["adi_soyadi"],
                sinifsube=r["sinifsube"],
                sira_no=r["sira_no"],
                durum=durum,
                kaydeden=request.user,
            ))

        SinavSalonYoklama.objects.bulk_create(yeni_kayitlar, ignore_conflicts=True)

        messages.success(
            request,
            f"Simülasyon tamamlandı: {len(kayitlar) - haric_count} uygun öğrenciden "
            f"{yok_count} devamsız ({devamsizlik_yuzdesi}%), "
            f"{mevcut_count} mevcut kaydedildi. "
            f"{haric_count} özel durumlu öğrenci (sürekli devamsız/muaf) atlandı."
        )
        return redirect("sinav:mazeret_yoklama_simule")

    return render(request, "sinav/mazeret_yoklama_simule.html", {
        "aktif_sinav":          aktif_sinav,
        "aktif_uretim":         aktif_uretim,
        "oturum_listesi":       oturum_listesi,
        "toplam_oturum":        toplam_oturum,
        "toplam_ogrenci":       toplam_ogrenci,
        "toplam_haric":         toplam_haric,
        "toplam_uygun":         toplam_ogrenci - toplam_haric,
        "yoklama_kayit_sayisi": yoklama_kayit_sayisi,
        "yok_sayisi":           yok_sayisi,
    })


# ===========================================================================
# Mazeret Sınavı
# ===========================================================================

@ust_yonetici_required
def mazeret_sinav_listesi(request):
    """
    Mazeret Sınavı ana sayfası (hub): Yoklama / Belge-Özel Durum / Planlama adımlarına
    giden, her biri kendi sayfasına yönlendiren üç kart gösterir.
    """
    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )
    planlar = (
        MazeretSinav.objects.filter(sinav=aktif_sinav)
        if aktif_sinav else []
    )
    son_mazeret = planlar.first() if planlar else None

    yok_sayisi = (
        SinavSalonYoklama.objects.filter(uretim=aktif_uretim, durum="yok")
        .values("okulno").distinct().count()
        if aktif_uretim else 0
    )
    belge_ctx = _mazeret_belge_ctx(son_mazeret) if son_mazeret else {}

    return render(request, "sinav/mazeret_listesi.html", {
        "aktif_sinav":  aktif_sinav,
        "planlar":      planlar,
        "son_mazeret":  son_mazeret,
        "yok_sayisi":   yok_sayisi,
        "toplam":       belge_ctx.get("toplam", 0),
        "uygun_n":      belge_ctx.get("uygun_n", 0),
    })


@ust_yonetici_required
def mazeret_yoklama(request):
    """
    Okulno veya adı-soyadı ile öğrenci arayıp, o öğrencinin aktif sınavdaki TÜM
    oturumlarının yoklamasını (mevcut/yok/geç) tek ekrandan girmeyi/düzenlemeyi
    sağlar (oda/salon bazlı gezinmek yerine).
    """
    from django.db.models import Q

    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    if request.method == "POST" and request.POST.get("form") == "yoklama_kaydet":
        okulno = request.POST.get("okulno", "").strip()
        n = int(request.POST.get("satir_sayisi", 0) or 0)
        if aktif_uretim and okulno:
            op_lookup = {
                (o.tarih, o.saat, o.salon): o
                for o in OturmaPlani.objects.filter(uretim=aktif_uretim, okulno=okulno)
            }
            adi_soyadi = ""
            for i in range(n):
                tarih_str = request.POST.get(f"tarih_{i}", "")
                saat      = request.POST.get(f"saat_{i}", "")
                salon     = request.POST.get(f"salon_{i}", "")
                durum     = request.POST.get(f"durum_{i}", "mevcut")
                try:
                    tarih = date.fromisoformat(tarih_str)
                except ValueError:
                    continue
                o = op_lookup.get((tarih, saat, salon))
                if not o:
                    continue
                adi_soyadi = o.adi_soyadi
                SinavSalonYoklama.objects.update_or_create(
                    uretim=aktif_uretim, tarih=tarih, saat=saat, salon=salon, okulno=okulno,
                    defaults={
                        "adi_soyadi": o.adi_soyadi,
                        "sinifsube":  o.sinifsube,
                        "sira_no":    o.sira_no,
                        "durum":      durum,
                        "kaydeden":   request.user,
                    },
                )
            messages.success(request, f"{adi_soyadi or okulno} için yoklama kaydedildi.")
        return redirect(f"{reverse('sinav:mazeret_yoklama')}?q={okulno}")

    yoklama_q       = request.GET.get("q", "").strip()
    yoklama_adaylar = []
    yoklama_ogrenci = None
    yoklama_oturumlar = []

    if aktif_uretim and yoklama_q:
        adaylar = list(
            OturmaPlani.objects.filter(uretim=aktif_uretim)
            .filter(Q(okulno__icontains=yoklama_q) | Q(adi_soyadi__icontains=yoklama_q))
            .values("okulno", "adi_soyadi", "sinifsube")
            .distinct()
            .order_by("adi_soyadi")
        )
        if len(adaylar) == 1:
            yoklama_ogrenci = adaylar[0]
        else:
            yoklama_adaylar = adaylar

    if aktif_uretim and yoklama_ogrenci:
        okulno = yoklama_ogrenci["okulno"]
        qs = (
            OturmaPlani.objects
            .filter(uretim=aktif_uretim, okulno=okulno)
            .order_by("tarih", "saat")
        )
        mevcut_yoklama = {
            (y.tarih, y.saat, y.salon): y.durum
            for y in SinavSalonYoklama.objects.filter(uretim=aktif_uretim, okulno=okulno)
        }
        for o in qs:
            yoklama_oturumlar.append({
                "tarih":     o.tarih,
                "saat":      o.saat,
                "salon":     o.salon,
                "ders_adi":  o.ders_adi,
                "durum":     mevcut_yoklama.get((o.tarih, o.saat, o.salon), "mevcut"),
            })

    return render(request, "sinav/mazeret_yoklama.html", {
        "aktif_sinav":       aktif_sinav,
        "yoklama_q":         yoklama_q,
        "yoklama_adaylar":   yoklama_adaylar,
        "yoklama_ogrenci":   yoklama_ogrenci,
        "yoklama_oturumlar": yoklama_oturumlar,
    })


@ust_yonetici_required
def mazeret_belge(request):
    """
    Aktif sınavın en son mazeret planı için belge teslim ve özel durum
    (sürekli devamsız / muaf) işaretlemesini sağlar.
    """
    aktif_sinav = SinavBilgisi.objects.filter(aktif=True).first()
    planlar = (
        MazeretSinav.objects.filter(sinav=aktif_sinav)
        if aktif_sinav else []
    )
    son_mazeret = planlar.first() if planlar else None

    if request.method == "POST" and request.POST.get("form") == "belge_kaydet":
        if son_mazeret:
            guncellenen_belge, guncellenen_ogr = _mazeret_belge_kaydet(request, son_mazeret)
            messages.success(
                request,
                f"Güncellendi: {guncellenen_belge} belge teslim, {guncellenen_ogr} öğrenci durumu."
            )
        belge_q = request.POST.get("belge_q", "").strip()
        return redirect(f"{reverse('sinav:mazeret_belge')}?belge_q={belge_q}")

    belge_q = request.GET.get("belge_q", "").strip()
    belge_ctx = _mazeret_belge_ctx(son_mazeret, belge_q) if son_mazeret else {}

    return render(request, "sinav/mazeret_belge.html", {
        "aktif_sinav": aktif_sinav,
        "belge_q":     belge_q,
        "son_mazeret": son_mazeret,
        **belge_ctx,
    })


@ust_yonetici_required
def mazeret_planlama(request):
    """Aktif sınava ait mazeret sınav planlarını listeler."""
    aktif_sinav = SinavBilgisi.objects.filter(aktif=True).first()
    planlar = (
        MazeretSinav.objects.filter(sinav=aktif_sinav)
        .prefetch_related("gunler__oturumlar__dersler__ders")
        if aktif_sinav else []
    )
    return render(request, "sinav/mazeret_planlama.html", {
        "aktif_sinav": aktif_sinav,
        "planlar":     planlar,
    })


@ust_yonetici_required
def mazeret_sinav_olustur(request):
    """
    Yeni mazeret sınav planı oluşturur.
    ILP motoru başlangıç tarihinden itibaren çakışmasız takvim üretir.
    """
    from .services.mazeret_dagitim import populate_ogrenciler
    from .services.mazeret_ilp import MazeretILPService

    aktif_sinav = SinavBilgisi.objects.filter(aktif=True).first()
    if not aktif_sinav:
        messages.error(request, "Aktif sınav bulunamadı.")
        return redirect("sinav:mazeret_listesi")

    if request.method == "POST":
        form = MazeretSinavForm(request.POST)
        if form.is_valid():
            mazeret = form.save(commit=False)
            mazeret.sinav = aktif_sinav
            mazeret.save()

            baslangic = form.cleaned_data["baslangic_tarihi"]
            oturum_saatleri = form.cleaned_data["oturum_saatleri"]
            tatil_gunleri = form.cleaned_data["tatil_gunleri"]

            # Öğrenci listesini yoklama verilerinden doldur
            # (sureksiz_devamsiz ve muaf öğrenciler otomatik hariç tutulur)
            eklenen, haric = populate_ogrenciler(mazeret)

            # ILP ile çakışmasız takvim üret
            svc = MazeretILPService(
                config={
                    "TIME_LIMIT": 120,
                    "MAX_SINAV_PER_GUN": mazeret.efektif_max_sinav_per_gun,
                },
                log_fn=lambda m: None,
            )
            basarili, mesaj = svc.calistir(
                mazeret_sinav=mazeret,
                baslangic_tarih=baslangic,
                oturum_saatleri_str=oturum_saatleri,
                tatil_gunleri_str=tatil_gunleri,
            )

            if basarili:
                haric_notu = f" ({haric} özel durumlu öğrenci hariç tutuldu.)" if haric else ""
                messages.success(request, f"Mazeret sınav planı oluşturuldu. {mesaj}{haric_notu}")
            else:
                messages.warning(request, f"Plan kaydedildi fakat ILP hatası: {mesaj}")

            return redirect("sinav:mazeret_detay", pk=mazeret.pk)
    else:
        # Varsayılan oturum saatlerini ve günlük oturum sınırını AlgoritmaParametreleri'nden al
        varsayilan_saatler = "08:50,10:30,12:10,13:35,14:25"
        varsayilan_max_gun = MazeretSinav.VARSAYILAN_MAX_SINAV_PER_GUN
        try:
            varsayilan_saatler = aktif_sinav.parametreler.oturum_saatleri
            varsayilan_max_gun = aktif_sinav.parametreler.max_sinav_per_gun
        except Exception:
            pass

        # Başlangıç tarihi önerisi: ana takvimin son gününden 5 iş günü sonrası
        from datetime import timedelta as _td
        aktif_uretim = TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        oneri_tarih = None
        if aktif_uretim:
            son_gun = (
                Takvim.objects.filter(uretim=aktif_uretim)
                .values_list("tarih", flat=True)
                .order_by("tarih")
                .last()
            )
            if son_gun:
                aday = son_gun + _td(days=5)
                while aday.weekday() >= 5:
                    aday += _td(days=1)
                oneri_tarih = aday

        form = MazeretSinavForm(initial={
            "oturum_saatleri": varsayilan_saatler,
            "baslangic_tarihi": oneri_tarih,
            "salon_config_text": "Mazeret 1:36\nMazeret 2:36",
            "max_sinav_per_gun": varsayilan_max_gun,
        })

    aktif_uretim = TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
    return render(request, "sinav/mazeret_olustur.html", {
        "aktif_sinav": aktif_sinav,
        "form": form,
        "aktif_uretim": aktif_uretim,
    })


@ust_yonetici_required
def mazeret_sinav_detay(request, pk):
    """Mazeret sınav planının detayını gösterir (günler, oturumlar, dersler, öğrenciler)."""
    mazeret = get_object_or_404(MazeretSinav, pk=pk)

    aktif_uretim = TakvimUretim.objects.filter(
        sinav=mazeret.sinav, aktif=True
    ).first()

    # Öğrenci listesini MazeretOgrenci'den oluştur:
    # {(ders_id, sinav_turu): [{"okulno", "adi_soyadi", "sinifsube"}, ...]}
    # MazeretOgrenci zaten sureksiz_devamsiz filtreli ve tekildir.
    ogrenci_map: dict[tuple, list] = {}
    if aktif_uretim:
        # ders_adi → ders_id çözümlemesi için cache
        ders_id_cache: dict[tuple[str, str], int | None] = {}

        for mo in MazeretOgrenci.objects.filter(mazeret_sinav=mazeret).order_by("sinifsube", "okulno"):
            cache_key = (mo.ders_adi, mo.sinav_turu)
            if cache_key not in ders_id_cache:
                tk = Takvim.objects.filter(
                    uretim=aktif_uretim,
                    ders__ders_adi=mo.ders_adi,
                    sinav_turu=mo.sinav_turu,
                ).values("ders_id").first()
                ders_id_cache[cache_key] = tk["ders_id"] if tk else None

            ders_id = ders_id_cache[cache_key]
            if ders_id is None:
                continue
            key = (ders_id, mo.sinav_turu)
            ogrenci_map.setdefault(key, []).append({
                "okulno":     mo.okulno,
                "adi_soyadi": mo.adi_soyadi,
                "sinifsube":  mo.sinifsube,
            })

    gunler = (
        mazeret.gunler
        .prefetch_related("oturumlar__dersler__ders")
        .order_by("tarih")
    )

    # Oturum bazında ders + öğrenci listesini hazırla
    gunler_veri = []
    for gun in gunler:
        oturumlar_veri = []
        for oturum in gun.oturumlar.order_by("oturum_no"):
            dersler_veri = []
            for od in oturum.dersler.select_related("ders").order_by("ders__ders_adi"):
                key = (od.ders_id, od.sinav_turu)
                dersler_veri.append({
                    "od":        od,
                    "ogrenciler": ogrenci_map.get(key, []),
                })
            oturumlar_veri.append({"oturum": oturum, "dersler": dersler_veri})
        gunler_veri.append({"gun": gun, "oturumlar": oturumlar_veri})

    return render(request, "sinav/mazeret_detay.html", {
        "mazeret":     mazeret,
        "gunler_veri": gunler_veri,
    })


def _mazeret_belge_kaydet(request, mazeret: MazeretSinav) -> tuple[int, int]:
    """
    POST'taki belge_teslim / sureksiz_devamsiz checkbox listelerinden MazeretOgrenci ve
    Ogrenci kayıtlarını günceller; belge_teslim değişikliklerini kalıcı MazeretBelgeTeslim
    tablosuna da yansıtır. (güncellenen_belge, güncellenen_ogr) döner.
    """
    from ogrenci.models import Ogrenci as OgrenciModel

    belge_isaretli    = set(map(int, request.POST.getlist("belge_teslim")))
    sureksiz_isaretli = set(request.POST.getlist("sureksiz_devamsiz"))
    guncellenen_belge = 0
    belge_ekle = []
    belge_sil_keys = []
    for mo in MazeretOgrenci.objects.filter(mazeret_sinav=mazeret):
        yeni_belge = mo.pk in belge_isaretli
        if mo.belge_teslim != yeni_belge:
            mo.belge_teslim = yeni_belge
            mo.save(update_fields=["belge_teslim"])
            guncellenen_belge += 1
        # Kalıcı tabloya da yansıt
        if yeni_belge:
            belge_ekle.append(
                MazeretBelgeTeslim(
                    okulno=mo.okulno,
                    ders_adi=mo.ders_adi,
                    sinav_turu=mo.sinav_turu,
                )
            )
        else:
            belge_sil_keys.append((mo.okulno, mo.ders_adi, mo.sinav_turu))

    sinav = mazeret.sinav
    if belge_ekle:
        for b in belge_ekle:
            b.sinav = sinav
        MazeretBelgeTeslim.objects.bulk_create(belge_ekle, ignore_conflicts=True)
    for okulno, ders_adi, sinav_turu in belge_sil_keys:
        MazeretBelgeTeslim.objects.filter(
            sinav=sinav, okulno=okulno, ders_adi=ders_adi, sinav_turu=sinav_turu
        ).delete()

    # Subquery yerine Python listesi: Ogrenci.okulno (int) ↔ MazeretOgrenci.okulno (varchar)
    _mo_okulno_ints = [
        int(x) for x in
        MazeretOgrenci.objects.filter(mazeret_sinav=mazeret)
        .values_list("okulno", flat=True).distinct() if x
    ]
    guncellenen_ogr = 0
    for ogr in (OgrenciModel.objects.filter(okulno__in=_mo_okulno_ints) if _mo_okulno_ints else OgrenciModel.objects.none()):
        yeni_sureksiz = str(ogr.okulno) in sureksiz_isaretli
        if ogr.sureksiz_devamsiz != yeni_sureksiz:
            ogr.sureksiz_devamsiz = yeni_sureksiz
            ogr.save(update_fields=["sureksiz_devamsiz"])
            guncellenen_ogr += 1

    return guncellenen_belge, guncellenen_ogr


def _mazeret_belge_ctx(mazeret: MazeretSinav, q: str = "") -> dict:
    """
    MazeretOgrenci tablosundan ders bazlı gruplu belge-teslim verisini (sureksiz/muaf
    bayrakları ve özet sayılarla) hazırlar. q verilirse okulno/adı-soyadı ile filtreler.
    """
    from django.db.models import Q

    from ogrenci.models import Ogrenci as OgrenciModel
    from ogrenci.models import OgrenciMuaf
    from okul.utils import get_aktif_egitim_yili

    # Sürekli devamsız okulnoları — int → str (MazeretOgrenci.okulno CharField)
    sureksiz_okulnolari = {
        str(x) for x in
        OgrenciModel.objects.filter(sureksiz_devamsiz=True).values_list("okulno", flat=True)
    }

    # Muaf (ders bazında): subquery yerine Python listesi (int↔varchar tip uyumu)
    _mo_ok_ints = [
        int(x) for x in
        MazeretOgrenci.objects.filter(mazeret_sinav=mazeret)
        .values_list("okulno", flat=True).distinct() if x
    ]
    muaf_okulno_ders: set[tuple[str, str]] = (
        {
            (str(ok), ders)
            for ok, ders in OgrenciMuaf.objects.filter(
                ogrenci__okulno__in=_mo_ok_ints,
                egitim_yili=get_aktif_egitim_yili(),
            ).values_list("ogrenci__okulno", "ders__ders_adi")
        }
        if _mo_ok_ints else set()
    )

    qs = MazeretOgrenci.objects.filter(mazeret_sinav=mazeret)
    if q:
        qs = qs.filter(Q(okulno__icontains=q) | Q(adi_soyadi__icontains=q))
    tum_ogrenciler = list(qs.order_by("ders_adi", "sinav_turu", "sinifsube", "okulno"))

    ders_map: dict[tuple, dict] = {}
    for mo in tum_ogrenciler:
        key = (mo.ders_adi, mo.sinav_turu)
        if key not in ders_map:
            ders_map[key] = {"ders_adi": mo.ders_adi, "sinav_turu": mo.sinav_turu, "ogrenciler": []}
        sureksiz = mo.okulno in sureksiz_okulnolari
        muaf = (mo.okulno, mo.ders_adi) in muaf_okulno_ders
        ders_map[key]["ogrenciler"].append({
            "mo":       mo,
            "sureksiz": sureksiz,
            "muaf":     muaf,
        })

    toplam         = len(tum_ogrenciler)
    belge_teslim_n = sum(1 for mo in tum_ogrenciler if mo.belge_teslim)
    haric_n = sum(
        1 for mo in tum_ogrenciler
        if mo.okulno in sureksiz_okulnolari or (mo.okulno, mo.ders_adi) in muaf_okulno_ders
    )
    uygun_n = sum(
        1 for mo in tum_ogrenciler
        if mo.belge_teslim
        and mo.okulno not in sureksiz_okulnolari
        and (mo.okulno, mo.ders_adi) not in muaf_okulno_ders
    )

    return {
        "ders_gruplar":   list(ders_map.values()),
        "toplam":         toplam,
        "belge_teslim_n": belge_teslim_n,
        "haric_n":        haric_n,
        "uygun_n":        uygun_n,
    }


@ust_yonetici_required
def mazeret_ogrenci_listesi(request, pk):
    """
    Mazeret sınavına aday öğrencilerin listesi:
    - Sürekli devamsız işaretleme (Ogrenci.sureksiz_devamsiz)
    - Belge teslim işaretleme (MazeretOgrenci.belge_teslim)
    """
    mazeret = get_object_or_404(MazeretSinav, pk=pk)

    if request.method == "POST":
        guncellenen_belge, guncellenen_ogr = _mazeret_belge_kaydet(request, mazeret)
        messages.success(
            request,
            f"Güncellendi: {guncellenen_belge} belge teslim, {guncellenen_ogr} öğrenci durumu."
        )
        return redirect("sinav:mazeret_ogrenci_listesi", pk=pk)

    return render(request, "sinav/mazeret_ogrenci_listesi.html", {
        "mazeret": mazeret,
        **_mazeret_belge_ctx(mazeret),
    })


@ust_yonetici_required
@require_POST
def mazeret_sinav_dagit(request, pk):
    """
    Öğrenci listesini günceller ve ILP ile yeniden dağıtır.
    baslangic_tarihi MazeretSinav üzerinde saklanır; eksikse form'dan alınır.
    """
    from .services.mazeret_dagitim import populate_ogrenciler
    from .services.mazeret_ilp import MazeretILPService

    mazeret = get_object_or_404(MazeretSinav, pk=pk)

    baslangic = mazeret.baslangic_tarihi
    if not baslangic:
        # POST parametresinden al (detay sayfasındaki formdan)
        from datetime import date as _date
        try:
            baslangic = _date.fromisoformat(request.POST.get("baslangic_tarihi", ""))
        except (ValueError, TypeError):
            hata = "Yeniden dağıtım için başlangıç tarihi gerekli. Lütfen bir tarih seçin."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": False, "mesaj": hata})
            messages.error(request, hata)
            return redirect("sinav:mazeret_detay", pk=pk)
        mazeret.baslangic_tarihi = baslangic
        mazeret.save(update_fields=["baslangic_tarihi"])

    oturum_saatleri = mazeret.oturum_saatleri or request.POST.get("oturum_saatleri", "")

    max_gun_raw = request.POST.get("max_sinav_per_gun", "").strip()
    if max_gun_raw:
        try:
            max_gun = max(1, int(max_gun_raw))
        except ValueError:
            max_gun = mazeret.efektif_max_sinav_per_gun
        else:
            if max_gun != mazeret.max_sinav_per_gun:
                mazeret.max_sinav_per_gun = max_gun
                mazeret.save(update_fields=["max_sinav_per_gun"])
    else:
        max_gun = mazeret.efektif_max_sinav_per_gun

    tatil_raw = request.POST.get("tatil_gunleri")
    if tatil_raw is not None and tatil_raw.strip() != mazeret.tatil_gunleri.strip():
        mazeret.tatil_gunleri = tatil_raw.strip()
        mazeret.save(update_fields=["tatil_gunleri"])

    eklenen, haric = populate_ogrenciler(mazeret)

    svc = MazeretILPService(
        config={"TIME_LIMIT": 120, "MAX_SINAV_PER_GUN": max_gun},
        log_fn=lambda m: None,
    )
    basarili, mesaj = svc.calistir(
        mazeret_sinav=mazeret,
        baslangic_tarih=baslangic,
        oturum_saatleri_str=oturum_saatleri,
        tatil_gunleri_str=mazeret.tatil_gunleri,
    )

    haric_notu = f" ({haric} özel durumlu öğrenci hariç tutuldu.)" if haric else ""

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": basarili, "mesaj": mesaj + haric_notu})

    if basarili:
        messages.success(request, mesaj + haric_notu)
    else:
        messages.error(request, mesaj)
    return redirect("sinav:mazeret_detay", pk=pk)


@ust_yonetici_required
@require_POST
def mazeret_sinav_sil(request, pk):
    """Mazeret sınav planını siler."""
    mazeret = get_object_or_404(MazeretSinav, pk=pk)
    mazeret.delete()
    messages.success(request, "Mazeret sınav planı silindi.")
    return redirect("sinav:mazeret_planlama")


# ---------------------------------------------------------------------------
# Mazeret Sınav Takvimi
# ---------------------------------------------------------------------------

def _mazeret_salon_gruplari(mazeret: MazeretSinav, kayitlar: list) -> list[dict]:
    """
    kayitlar listesini (MazeretOturmaPlani) salon adına göre gruplar.
    Sıralama önce mazeret.efektif_salon_config'deki salon adlarını, sonra kayıtlarda
    olup config'de olmayan (elle düzenlenmiş) salon adlarını takip eder.
    """
    salon_adlari = list(mazeret.efektif_salon_config.keys())
    for k in kayitlar:
        if k.salon not in salon_adlari:
            salon_adlari.append(k.salon)
    return [
        {"ad": ad, "kayitlar": [k for k in kayitlar if k.salon == ad]}
        for ad in salon_adlari
    ]


@ust_yonetici_required
@require_POST
def mazeret_takvim_olustur(request, pk):
    """Mazeret oturma planını oluşturur (salon atamaları kelebek dağılımla yapılır)."""
    from .services.mazeret_takvim import oturma_plani_olustur

    mazeret = get_object_or_404(MazeretSinav, pk=pk)
    sonuc = oturma_plani_olustur(mazeret)

    if sonuc["toplam"] == 0:
        messages.warning(request, "Takvime yerleştirilecek uygun öğrenci bulunamadı. "
                         "Öğrencilerin belge teslim durumunu kontrol edin.")
    else:
        salon_ozet = ", ".join(
            f"{ad}: {sayi}" for ad, sayi in sonuc["salonlar"].items()
        )
        msg = f"Takvim oluşturuldu: {sonuc['toplam']} öğrenci — {salon_ozet}."
        if sonuc["uyari"]:
            messages.warning(request, msg + " " + sonuc["uyari"])
        else:
            messages.success(request, msg)

    return redirect("sinav:mazeret_takvim", pk=pk)


@ust_yonetici_required
def mazeret_takvim_detay(request, pk):
    """Mazeret oturma planını gösterir ve düzenleme imkânı sunar."""
    mazeret = get_object_or_404(MazeretSinav, pk=pk)

    # POST: salon/sıra değişikliği
    if request.method == "POST" and not mazeret.onaylandi:
        kayit_id = request.POST.get("kayit_id")
        yeni_salon = request.POST.get("salon", "").strip()
        yeni_sira = request.POST.get("sira_no", "").strip()
        if kayit_id and yeni_salon and yeni_sira:
            try:
                kayit = MazeretOturmaPlani.objects.get(pk=kayit_id, mazeret_sinav=mazeret)
                kayit.salon = yeni_salon
                kayit.sira_no = int(yeni_sira)
                kayit.save()
                return JsonResponse({"ok": True})
            except (MazeretOturmaPlani.DoesNotExist, ValueError):
                return JsonResponse({"ok": False, "hata": "Kayıt bulunamadı."}, status=400)
        return JsonResponse({"ok": False, "hata": "Eksik parametre."}, status=400)

    # Takvim verisi: oturum → salon → [kayıtlar]
    oturumlar_qs = (
        MazeretOturum.objects
        .filter(gun__mazeret_sinav=mazeret)
        .prefetch_related("oturma_plani")
        .select_related("gun")
        .order_by("gun__tarih", "oturum_no")
    )

    oturumlar_veri = []
    for oturum in oturumlar_qs:
        kayitlar = list(oturum.oturma_plani.order_by("salon", "sira_no"))
        dersler = list(
            MazeretOturumDers.objects
            .filter(oturum=oturum)
            .select_related("ders")
            .order_by("ders__ders_adi")
        )
        oturumlar_veri.append({
            "oturum": oturum,
            "dersler": dersler,
            "salonlar": _mazeret_salon_gruplari(mazeret, kayitlar),
            "toplam": len(kayitlar),
        })

    return render(request, "sinav/mazeret_takvim.html", {
        "mazeret": mazeret,
        "oturumlar_veri": oturumlar_veri,
    })


@ust_yonetici_required
@require_POST
def mazeret_takvim_onayla(request, pk):
    """Mazeret takvimini onaylar; onaydan sonra düzenleme devre dışı kalır."""
    from django.utils import timezone as tz

    mazeret = get_object_or_404(MazeretSinav, pk=pk)
    if not MazeretOturmaPlani.objects.filter(mazeret_sinav=mazeret).exists():
        messages.error(request, "Önce takvimi oluşturun.")
        return redirect("sinav:mazeret_takvim", pk=pk)

    mazeret.onaylandi = True
    mazeret.onay_tarihi = tz.now()
    mazeret.save(update_fields=["onaylandi", "onay_tarihi"])
    messages.success(request, "Mazeret takvimi onaylandı. Artık rapor alınabilir.")
    return redirect("sinav:mazeret_takvim", pk=pk)


@ust_yonetici_required
@require_POST
def mazeret_takvim_onayli_iptal(request, pk):
    """Onayı geri alır (düzenleme için)."""
    mazeret = get_object_or_404(MazeretSinav, pk=pk)
    mazeret.onaylandi = False
    mazeret.onay_tarihi = None
    mazeret.save(update_fields=["onaylandi", "onay_tarihi"])
    messages.info(request, "Onay kaldırıldı. Takvim tekrar düzenlenebilir.")
    return redirect("sinav:mazeret_takvim", pk=pk)


@ust_yonetici_required
def mazeret_rapor(request, pk):
    """Onaylanmış mazeret takviminin yazdırılabilir raporu."""
    mazeret = get_object_or_404(MazeretSinav, pk=pk)

    oturumlar_qs = (
        MazeretOturum.objects
        .filter(gun__mazeret_sinav=mazeret)
        .select_related("gun")
        .order_by("gun__tarih", "oturum_no")
    )

    oturumlar_veri = []
    for oturum in oturumlar_qs:
        kayitlar = list(oturum.oturma_plani.order_by("salon", "sira_no"))
        dersler = list(
            MazeretOturumDers.objects
            .filter(oturum=oturum)
            .select_related("ders")
            .order_by("ders__ders_adi")
        )
        oturumlar_veri.append({
            "oturum": oturum,
            "dersler": dersler,
            "salonlar": _mazeret_salon_gruplari(mazeret, kayitlar),
            "toplam": len(kayitlar),
        })

    okul = OkulBilgi.get()
    return render(request, "sinav/mazeret_rapor.html", {
        "mazeret": mazeret,
        "oturumlar_veri": oturumlar_veri,
        "okul": okul,
    })


@ust_yonetici_required
def mazeret_rapor_pdf_view(request, pk):
    """Mazeret oturma planını PDF olarak indirir (ReportLab)."""
    import io

    from django.http import HttpResponse

    from ortaksinav_engine.services.pdf_rapor import mazeret_rapor_pdf

    mazeret = get_object_or_404(MazeretSinav, pk=pk)

    oturumlar_qs = (
        MazeretOturum.objects
        .filter(gun__mazeret_sinav=mazeret)
        .select_related("gun")
        .order_by("gun__tarih", "oturum_no")
    )
    oturumlar_veri = []
    for oturum in oturumlar_qs:
        kayitlar = list(oturum.oturma_plani.order_by("salon", "sira_no"))
        oturumlar_veri.append({
            "oturum": oturum,
            "dersler": list(
                MazeretOturumDers.objects
                .filter(oturum=oturum)
                .select_related("ders")
                .order_by("ders__ders_adi")
            ),
            "salonlar": _mazeret_salon_gruplari(mazeret, kayitlar),
        })

    okul = OkulBilgi.get()
    buf = io.BytesIO()
    mazeret_rapor_pdf(oturumlar_veri, buf, okul, mazeret)
    buf.seek(0)

    dosya_adi = f"mazeret_rapor_{pk}.pdf"
    response = HttpResponse(buf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dosya_adi}"'
    return response


def _mazeret_ilan_oturumlar_veri(mazeret: MazeretSinav) -> list[dict]:
    """İlan takvimi için gün/oturum/ders verisini (öğrenci/salon detayı olmadan) hazırlar."""
    oturumlar_qs = (
        MazeretOturum.objects
        .filter(gun__mazeret_sinav=mazeret)
        .select_related("gun")
        .order_by("gun__tarih", "oturum_no")
    )
    return [
        {
            "oturum": oturum,
            "dersler": list(
                MazeretOturumDers.objects
                .filter(oturum=oturum)
                .select_related("ders")
                .order_by("ders__ders_adi")
            ),
        }
        for oturum in oturumlar_qs
    ]


@ust_yonetici_required
def mazeret_ilan_takvimi(request, pk):
    """Mazeret sınavı gün/oturum/ders takvimini panoya asılabilir ilan formatında gösterir."""
    mazeret = get_object_or_404(MazeretSinav, pk=pk)
    return render(request, "sinav/mazeret_ilan.html", {
        "mazeret": mazeret,
        "oturumlar_veri": _mazeret_ilan_oturumlar_veri(mazeret),
        "okul": OkulBilgi.get(),
    })


@ust_yonetici_required
def mazeret_ilan_takvimi_pdf(request, pk):
    """Mazeret sınavı ilan takvimini PDF olarak indirir (ReportLab)."""
    import io

    from django.http import HttpResponse

    from ortaksinav_engine.services.pdf_rapor import mazeret_ilan_pdf

    mazeret = get_object_or_404(MazeretSinav, pk=pk)
    buf = io.BytesIO()
    mazeret_ilan_pdf(_mazeret_ilan_oturumlar_veri(mazeret), buf, OkulBilgi.get(), mazeret)
    buf.seek(0)

    dosya_adi = f"mazeret_ilan_{pk}.pdf"
    response = HttpResponse(buf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dosya_adi}"'
    return response


# ---------------------------------------------------------------------------
# Öğretmen: kendi sorumluluk sınav görevleri
# ---------------------------------------------------------------------------

@login_required
def sorumluluk_gorevlerim(request):
    from django.db.models import Q

    from sorumluluk.models import (
        SALON_CHOICES,
        SorumluGozetmen,
        SorumluKomisyonUyesi,
        SorumluTakvim,
    )

    try:
        personel = request.user.personel
    except Exception:
        personel = None

    sinav_gorevler = []

    if personel:
        salon_label = dict(SALON_CHOICES)

        takvim_saatler = {
            (t.sinav_id, t.tarih, t.oturum_no): (t.saat_baslangic, t.saat_bitis)
            for t in SorumluTakvim.objects.order_by("sinav_id", "tarih", "oturum_no")
        }

        sinav_map: dict = {}

        for ku in (SorumluKomisyonUyesi.objects
                   .filter(Q(uye1=personel) | Q(uye2=personel))
                   .select_related("sinav", "sinav__egitim_yili")
                   .order_by("sinav__olusturma_tarihi", "tarih", "oturum_no")):
            sid = ku.sinav_id
            if sid not in sinav_map:
                sinav_map[sid] = {"sinav": ku.sinav, "gorevler": []}
            saatler = takvim_saatler.get((sid, ku.tarih, ku.oturum_no))
            sinav_map[sid]["gorevler"].append({
                "tarih":          ku.tarih,
                "oturum_no":      ku.oturum_no,
                "saat_baslangic": saatler[0] if saatler else None,
                "saat_bitis":     saatler[1] if saatler else None,
                "tur":            "Komisyon Üyesi",
                "detay":          ku.ders_adi,
            })

        for gz in (SorumluGozetmen.objects
                   .filter(gozetmen=personel)
                   .select_related("sinav", "sinav__egitim_yili")
                   .order_by("sinav__olusturma_tarihi", "tarih", "oturum_no")):
            sid = gz.sinav_id
            if sid not in sinav_map:
                sinav_map[sid] = {"sinav": gz.sinav, "gorevler": []}
            saatler = takvim_saatler.get((sid, gz.tarih, gz.oturum_no))
            sinav_map[sid]["gorevler"].append({
                "tarih":          gz.tarih,
                "oturum_no":      gz.oturum_no,
                "saat_baslangic": saatler[0] if saatler else None,
                "saat_bitis":     saatler[1] if saatler else None,
                "tur":            "Gözetmen",
                "detay":          salon_label.get(gz.salon, gz.salon),
            })

        for data in sinav_map.values():
            data["gorevler"].sort(key=lambda x: (x["tarih"], x["oturum_no"], x["tur"]))
            data["komisyon_sayi"] = sum(1 for g in data["gorevler"] if g["tur"] == "Komisyon Üyesi")
            data["gozetmen_sayi"] = sum(1 for g in data["gorevler"] if g["tur"] == "Gözetmen")

        sinav_gorevler = sorted(
            sinav_map.values(),
            key=lambda d: d["sinav"].olusturma_tarihi or d["sinav"].pk,
        )

    return render(request, "sinav/sorumluluk_gorevlerim.html", {
        "personel":      personel,
        "sinav_gorevler": sinav_gorevler,
    })
