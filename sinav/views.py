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
from sinav.services.ders_ayarlari import (
    _VARSAYILAN_CATISMA_GRUBU,
    _VARSAYILAN_CIFT_OTURUMLU,
    _VARSAYILAN_SINAV_YAPILMAYACAK,
    get_ayarlar,
    mutate_ayar_listesi,
    parse_ders_ayarlari_post,
    save_ayarlar,
)
from sinav.services.mazeret_belge import mazeret_belge_ctx, mazeret_belge_kaydet
from sinav.services.mazeret_rapor import (
    mazeret_detay_verisi,
    mazeret_ilan_oturumlar_veri,
    mazeret_oturumlar_verisi,
)
from sinav.services.mazeret_yoklama import (
    oturum_istatistikleri,
    yoklama_getir,
    yoklama_kaydet,
    yoklama_simulasyonu_calistir,
)
from sinav.services.ogrenci_sorgu import en_yakin_sinav_sonucu
from sinav.services.oturma_pdf import build_salon_grids, resolve_aktif_uretim
from sinav.services.sinav_ozet import db_ozeti, gozetmen_ozeti_hesapla, sinav_takvim_araliklari
from sinav.services.takvim_duzenleme import (
    onizleme_oturumlarini_yeniden_numarala,
    takvim_oturumlarini_yeniden_numarala,
    takvimi_onayla,
)
from sinav.services.takvim_slot import slot_temizle
from sinav.services.yoklama_rapor import (
    turkce_tarih_ayristir,
    yok_ogrenciler_gruplu,
    yoklama_dersleri,
    yoklama_ogrenci_listesi_hesapla,
    yoklama_satirlari_hesapla,
)

from .forms import AlgoritmaForm, MazeretSinavForm, SinavBilgisiForm
from .models import (
    AlgoritmaParametreleri,
    DisVeri,
    MazeretOturmaPlani,
    MazeretSinav,
    OturmaPlani,
    SinavBilgisi,
    SinavSalonYoklama,
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
    from datetime import datetime as _dt

    from ortaksinav_engine.services.pdf_rapor import oturum_plani_pdf
    from sinav.models import OturmaPlani

    tarih_str  = request.GET.get("tarih", "")
    saat       = request.GET.get("saat", "")
    oturum     = int(request.GET.get("oturum", 1))
    uretim_pk  = request.GET.get("uretim")
    try:
        tarih_date = _dt.strptime(tarih_str, "%Y-%m-%d").date()
    except ValueError:
        raise Http404

    aktif_uretim = resolve_aktif_uretim(uretim_pk, tarih_date, saat, oturum, _aktif_sinav())
    if uretim_pk and aktif_uretim is None:
        raise Http404

    salon_filter = request.GET.get("salon", "")
    qs = OturmaPlani.objects.filter(
        tarih=tarih_date, saat=saat, oturum=oturum, uretim=aktif_uretim
    )
    if salon_filter:
        qs = qs.filter(salon=salon_filter)
    qs = qs.order_by("salon", "sira_no")
    if not qs.exists():
        raise Http404

    salon_grids = build_salon_grids(qs)

    baslik = f"{tarih_str} {saat} (Oturum {oturum})"
    okul   = OkulBilgi.get()
    buf    = io.BytesIO()
    oturum_plani_pdf(salon_grids, buf, baslik, okul, aktif_uretim, tarih=tarih_date, saat=saat)
    buf.seek(0)
    fname = f"Oturma_Plani_{tarih_str}_{saat.replace(':', '')}.pdf"
    return HttpResponse(buf.read(), content_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})


def _sinav_takvimi_pdf_response(request, goster_subeler: bool):
    import io

    from ortaksinav_engine.services.pdf_rapor import sinav_takvimi_pdf
    from sinav.models import Takvim as TakvimModel
    from sinav.models import TakvimUretim

    aktif = _aktif_sinav()
    if not aktif:
        raise Http404

    aktif_uretim = TakvimUretim.objects.filter(sinav=aktif, aktif=True).first()
    if not aktif_uretim:
        raise Http404

    TakvimModel.objects.filter(sinav=aktif, uretim__isnull=True).update(uretim=aktif_uretim)

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
def sinav_takvimi_pdf_view(request):
    """Aktif TakvimUretim'e bağlı tek sayfalık öğrenci Sınav Takvimi PDF'i döner.
    ?subeler=0  →  Şubeler sütunu olmadan üretir (varsayılan: şubeli).
    """
    goster_subeler = request.GET.get("subeler", "1") != "0"
    return _sinav_takvimi_pdf_response(request, goster_subeler)


@login_required
def sinav_takvimi_subesiz_pdf_view(request):
    """Şubeler sütunu olmadan sınav takvimi PDF'i döner."""
    return _sinav_takvimi_pdf_response(request, goster_subeler=False)


@login_required
def sinif_listesi_pdf_view(request):
    """OturmaPlani DB'den Sınıf Listesi PDF'ini anlık üretip döner."""
    import io
    from datetime import datetime as _dt

    from ortaksinav_engine.services.pdf_rapor import sinif_raporu_pdf
    from sinav.models import OturmaPlani

    tarih_str      = request.GET.get("tarih", "")
    saat           = request.GET.get("saat", "")
    oturum         = int(request.GET.get("oturum", 1))
    uretim_pk      = request.GET.get("uretim")
    sinifsube_filtre = request.GET.get("sinifsube", "") or None
    try:
        tarih_date = _dt.strptime(tarih_str, "%Y-%m-%d").date()
    except ValueError:
        raise Http404

    aktif_uretim = resolve_aktif_uretim(uretim_pk, tarih_date, saat, oturum, _aktif_sinav())
    if uretim_pk:
        if aktif_uretim is None:
            raise Http404
    elif not OturmaPlani.objects.filter(
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
@login_required
def ders_ayarlari(request):
    from okul.models import DersHavuzu
    aktif = _aktif_sinav()
    veri = get_ayarlar(aktif)

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

    veri = get_ayarlar(aktif)
    veri.update(parse_ders_ayarlari_post(request.POST))
    save_ayarlar(aktif, veri)

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
    if tip == "yapilmayacak":
        def _mutate(liste):
            liste[:] = sorted(set(liste) | set(_VARSAYILAN_SINAV_YAPILMAYACAK))
            return True
        mutate_ayar_listesi(aktif, "yapilmayacak", _mutate)
        messages.success(request, "Varsayılan 'sınav yapılmayacak' listesi yüklendi.")
    elif tip == "cift":
        def _mutate(liste):
            liste[:] = sorted(set(liste) | set(_VARSAYILAN_CIFT_OTURUMLU))
            return True
        mutate_ayar_listesi(aktif, "cift_oturumlu", _mutate)
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

    def _mutate(liste):
        yeni = {"ders_adi": ders_adi, "tarih": tarih, "saat": saat, "seviyeler": seviyeler}
        for i, ss in enumerate(liste):
            if ss["ders_adi"] == ders_adi:
                liste[i] = yeni
                return True
        liste.append(yeni)
        return False

    guncellendi = mutate_ayar_listesi(aktif, "sabit_sinavlar", _mutate)
    if guncellendi:
        messages.success(request, f'"{ders_adi}" sabit sınav güncellendi.')
    else:
        messages.success(request, f'"{ders_adi}" sabit sınav olarak eklendi.')
    return redirect("sinav:ders_ayarlari")


@require_POST
def sabit_sinav_sil(request, idx: int):
    aktif = _aktif_sinav()

    def _mutate(liste):
        if 0 <= idx < len(liste):
            ad = liste[idx]["ders_adi"]
            liste.pop(idx)
            return ad
        return None

    sonuc = mutate_ayar_listesi(aktif, "sabit_sinavlar", _mutate)
    if sonuc:
        messages.success(request, f'"{sonuc}" sabit sınavdan çıkarıldı.')
    else:
        messages.error(request, "Kayıt bulunamadı.")
    return redirect("sinav:ders_ayarlari")


# ---------------------------------------------------------------
# Seviye Çakışma Grupları
# ---------------------------------------------------------------
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

    def _mutate(liste):
        liste.append({"grup_adi": grup_adi, "dersler": ders_listesi})
        return True

    mutate_ayar_listesi(aktif, "catisma_gruplari", _mutate)
    messages.success(request, f'"{grup_adi}" çakışma grubu eklendi ({len(ders_listesi)} ders).')
    return redirect("sinav:ders_ayarlari")


@require_POST
def catisma_grubu_sil(request, idx: int):
    aktif = _aktif_sinav()

    def _mutate(liste):
        if 0 <= idx < len(liste):
            ad = liste[idx]["grup_adi"]
            liste.pop(idx)
            return ad
        return None

    sonuc = mutate_ayar_listesi(aktif, "catisma_gruplari", _mutate)
    if sonuc:
        messages.success(request, f'"{sonuc}" çakışma grubu silindi.')
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

    def _mutate(liste):
        liste.append({"grup_adi": _VARSAYILAN_CATISMA_GRUBU["grup_adi"], "dersler": ders_listesi})
        return True

    mutate_ayar_listesi(aktif, "catisma_gruplari", _mutate)
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

    def _mutate(liste):
        if any(e["ders1"] == ders1 and e["ders2"] == ders2 for e in liste):
            return None
        liste.append({"ders1": ders1, "ders2": ders2})
        return True

    sonuc = mutate_ayar_listesi(aktif, "ayni_slot_esleme", _mutate)
    if sonuc:
        messages.success(request, f'"{ders1}" ↔ "{ders2}" eşlemesi eklendi.')
    else:
        messages.info(request, "Bu eşleme zaten kayıtlı.")
    return redirect("sinav:ders_ayarlari")


@require_POST
def esleme_sil(request, idx: int):
    aktif = _aktif_sinav()

    def _mutate(liste):
        if 0 <= idx < len(liste):
            liste.pop(idx)
            return True
        return None

    sonuc = mutate_ayar_listesi(aktif, "ayni_slot_esleme", _mutate)
    if sonuc:
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
            sonuclar, gosterim_tarihi, hata = en_yakin_sinav_sonucu(aktif_uretim, okulno, bugun)

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

    aktif_sinav  = _aktif_sinav()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    dersler = yoklama_dersleri(aktif_uretim)
    SEVIYELER = [9, 10, 11, 12]

    filtre_seviye  = request.GET.get("seviye", "").strip()
    filtre_ders_id = request.GET.get("ders_id", "").strip()

    filtre_ders_adi_base = None
    if aktif_uretim and filtre_ders_id:
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

    satirlar = yoklama_satirlari_hesapla(aktif_uretim, filtre_seviye, filtre_ders_adi_base)

    ogrenci_listesi = []
    if aktif_uretim and filtre_seviye and filtre_ders_id and filtre_ders_adi_base:
        ogrenci_listesi = yoklama_ogrenci_listesi_hesapla(aktif_uretim, filtre_seviye, filtre_ders_adi_base)

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
    from django.core.exceptions import PermissionDenied

    from okul.auth import is_ust_yonetici

    if not is_ust_yonetici(request.user):
        raise PermissionDenied

    seviye   = request.GET.get("seviye", "").strip()
    ders_adi = request.GET.get("ders_adi", "").strip()
    tarih    = turkce_tarih_ayristir(request.GET.get("tarih", "").strip())

    aktif_sinav  = _aktif_sinav()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    gruplar_liste = yok_ogrenciler_gruplu(aktif_uretim, seviye, ders_adi, tarih)

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
    from django.core.exceptions import PermissionDenied

    from okul.auth import is_ust_yonetici

    if not is_ust_yonetici(request.user):
        raise PermissionDenied

    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    istatistik = oturum_istatistikleri(aktif_uretim)

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

        sonuc = yoklama_simulasyonu_calistir(
            aktif_uretim, secili_keys, tumu_sec, devamsizlik_yuzdesi,
            mevcut_de_kaydet, sifirla_once, request.user,
        )

        messages.success(
            request,
            f"Simülasyon tamamlandı: {sonuc['toplam'] - sonuc['haric_count']} uygun öğrenciden "
            f"{sonuc['yok_count']} devamsız ({devamsizlik_yuzdesi}%), "
            f"{sonuc['mevcut_count']} mevcut kaydedildi. "
            f"{sonuc['haric_count']} özel durumlu öğrenci (sürekli devamsız/muaf) atlandı."
        )
        return redirect("sinav:mazeret_yoklama_simule")

    return render(request, "sinav/mazeret_yoklama_simule.html", {
        "aktif_sinav":  aktif_sinav,
        "aktif_uretim": aktif_uretim,
        **istatistik,
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
    belge_ctx = mazeret_belge_ctx(son_mazeret) if son_mazeret else {}

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
            satirlar = []
            for i in range(n):
                try:
                    tarih = date.fromisoformat(request.POST.get(f"tarih_{i}", ""))
                except ValueError:
                    continue
                satirlar.append({
                    "tarih": tarih,
                    "saat":  request.POST.get(f"saat_{i}", ""),
                    "salon": request.POST.get(f"salon_{i}", ""),
                    "durum": request.POST.get(f"durum_{i}", "mevcut"),
                })
            adi_soyadi = yoklama_kaydet(aktif_uretim, okulno, satirlar, request.user)
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
        yoklama_oturumlar = yoklama_getir(aktif_uretim, yoklama_ogrenci["okulno"])

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
            guncellenen_belge, guncellenen_ogr = mazeret_belge_kaydet(request, son_mazeret)
            messages.success(
                request,
                f"Güncellendi: {guncellenen_belge} belge teslim, {guncellenen_ogr} öğrenci durumu."
            )
        belge_q = request.POST.get("belge_q", "").strip()
        return redirect(f"{reverse('sinav:mazeret_belge')}?belge_q={belge_q}")

    belge_q = request.GET.get("belge_q", "").strip()
    belge_ctx = mazeret_belge_ctx(son_mazeret, belge_q) if son_mazeret else {}

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
    from .services.mazeret_planlama import ogrenci_doldur_ve_dagit, olustur_form_varsayilanlari

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

            basarili, mesaj, haric = ogrenci_doldur_ve_dagit(
                mazeret, baslangic, oturum_saatleri, tatil_gunleri,
                mazeret.efektif_max_sinav_per_gun,
            )

            if basarili:
                haric_notu = f" ({haric} özel durumlu öğrenci hariç tutuldu.)" if haric else ""
                messages.success(request, f"Mazeret sınav planı oluşturuldu. {mesaj}{haric_notu}")
            else:
                messages.warning(request, f"Plan kaydedildi fakat ILP hatası: {mesaj}")

            return redirect("sinav:mazeret_detay", pk=mazeret.pk)
    else:
        varsayilanlar = olustur_form_varsayilanlari(aktif_sinav)
        form = MazeretSinavForm(initial={
            "oturum_saatleri":    varsayilanlar["oturum_saatleri"],
            "baslangic_tarihi":   varsayilanlar["baslangic_tarihi"],
            "salon_config_text":  "Mazeret 1:36\nMazeret 2:36",
            "max_sinav_per_gun":  varsayilanlar["max_sinav_per_gun"],
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

    gunler_veri = mazeret_detay_verisi(mazeret, aktif_uretim)

    return render(request, "sinav/mazeret_detay.html", {
        "mazeret":     mazeret,
        "gunler_veri": gunler_veri,
    })


@ust_yonetici_required
def mazeret_ogrenci_listesi(request, pk):
    """
    Mazeret sınavına aday öğrencilerin listesi:
    - Sürekli devamsız işaretleme (Ogrenci.sureksiz_devamsiz)
    - Belge teslim işaretleme (MazeretOgrenci.belge_teslim)
    """
    mazeret = get_object_or_404(MazeretSinav, pk=pk)

    if request.method == "POST":
        guncellenen_belge, guncellenen_ogr = mazeret_belge_kaydet(request, mazeret)
        messages.success(
            request,
            f"Güncellendi: {guncellenen_belge} belge teslim, {guncellenen_ogr} öğrenci durumu."
        )
        return redirect("sinav:mazeret_ogrenci_listesi", pk=pk)

    return render(request, "sinav/mazeret_ogrenci_listesi.html", {
        "mazeret": mazeret,
        **mazeret_belge_ctx(mazeret),
    })


@ust_yonetici_required
@require_POST
def mazeret_sinav_dagit(request, pk):
    """
    Öğrenci listesini günceller ve ILP ile yeniden dağıtır.
    baslangic_tarihi MazeretSinav üzerinde saklanır; eksikse form'dan alınır.
    """
    from .services.mazeret_planlama import ogrenci_doldur_ve_dagit

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

    basarili, mesaj, haric = ogrenci_doldur_ve_dagit(
        mazeret, baslangic, oturum_saatleri, mazeret.tatil_gunleri, max_gun,
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

    return render(request, "sinav/mazeret_takvim.html", {
        "mazeret": mazeret,
        "oturumlar_veri": mazeret_oturumlar_verisi(mazeret),
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

    okul = OkulBilgi.get()
    return render(request, "sinav/mazeret_rapor.html", {
        "mazeret": mazeret,
        "oturumlar_veri": mazeret_oturumlar_verisi(mazeret),
        "okul": okul,
    })


@ust_yonetici_required
def mazeret_rapor_pdf_view(request, pk):
    """Mazeret oturma planını PDF olarak indirir (ReportLab)."""
    import io

    from django.http import HttpResponse

    from ortaksinav_engine.services.pdf_rapor import mazeret_rapor_pdf

    mazeret = get_object_or_404(MazeretSinav, pk=pk)

    okul = OkulBilgi.get()
    buf = io.BytesIO()
    mazeret_rapor_pdf(mazeret_oturumlar_verisi(mazeret), buf, okul, mazeret)
    buf.seek(0)

    dosya_adi = f"mazeret_rapor_{pk}.pdf"
    response = HttpResponse(buf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dosya_adi}"'
    return response


@ust_yonetici_required
def mazeret_ilan_takvimi(request, pk):
    """Mazeret sınavı gün/oturum/ders takvimini panoya asılabilir ilan formatında gösterir."""
    mazeret = get_object_or_404(MazeretSinav, pk=pk)
    return render(request, "sinav/mazeret_ilan.html", {
        "mazeret": mazeret,
        "oturumlar_veri": mazeret_ilan_oturumlar_veri(mazeret),
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
    mazeret_ilan_pdf(mazeret_ilan_oturumlar_veri(mazeret), buf, OkulBilgi.get(), mazeret)
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
    from sinav.services.sorumluluk_gorevlerim import gorevlerimi_hazirla

    try:
        personel = request.user.personel
    except Exception:
        personel = None

    return render(request, "sinav/sorumluluk_gorevlerim.html", {
        "personel":       personel,
        "sinav_gorevler": gorevlerimi_hazirla(personel),
    })
