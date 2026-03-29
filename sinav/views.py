import os
import uuid
import threading
import traceback
from datetime import datetime
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.db.models import Subquery, OuterRef
from .utils import gozetmen_bul, onceki_ders_saati

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse, FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import AlgoritmaForm, SinavBilgisiForm
from .models import (
    SinavBilgisi,
    DersAyarlariJSON,
    DisVeri, AlgoritmaParametreleri,
    TakvimUretim, OturmaPlani,
)
from okul.models import OkulBilgi
from ogrenci.models import Ogrenci as OgrenciModel
from dersprogrami.models import DersProgrami
from ortaksinav_engine import (
    CONFIG,
    temel_verileri_olustur,
    verileri_aktar,
    subeders_guncelle,
    takvim_olustur,
    oturma_planlarini_olustur,
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
# Session'dan CONFIG'e uygula
# ---------------------------------------------------------------
def _apply_config(session_cfg: dict):
    if session_cfg.get("eokul_ogrenci_dosya"):
        CONFIG["eokul_ogrenci_dosya"] = session_cfg["eokul_ogrenci_dosya"]
    if session_cfg.get("eokul_haftalik_program_dosya"):
        CONFIG["eokul_haftalik_program_dosya"] = session_cfg["eokul_haftalik_program_dosya"]
    if session_cfg.get("uygulama_tarihi"):
        CONFIG["uygulama_tarihi"] = session_cfg["uygulama_tarihi"]

    # Her sınav için ayrı çıktı klasörü: media/cikti/sinav_{pk}/
    aktif_sinav_cfg = SinavBilgisi.objects.filter(aktif=True).first()
    if aktif_sinav_cfg:
        CONFIG["cikti_klasor"] = str(Path(settings.MEDIA_ROOT) / "cikti" / f"sinav_{aktif_sinav_cfg.pk}")
    else:
        CONFIG["cikti_klasor"] = str(Path(settings.MEDIA_ROOT) / "cikti")

    # Algoritma parametreleri: DB birincil kaynak, yoksa session'a bak
    prm = AlgoritmaParametreleri.objects.filter(sinav=aktif_sinav_cfg).first() if aktif_sinav_cfg else None
    alg = prm.to_session_dict() if prm else session_cfg

    if alg.get("baslangic_tarih"):
        CONFIG["BASLANGIC_TARIH"] = datetime.fromisoformat(str(alg["baslangic_tarih"]))

    if alg.get("oturum_saatleri"):
        saatler = [s.strip() for s in alg["oturum_saatleri"].split(",") if s.strip()]
        CONFIG["OTURUM_SAATLERI"] = saatler
        CONFIG["OTURUM_SAYISI_GUN"] = len(saatler)

    if "time_limit_phase1" in alg:
        CONFIG["TIME_LIMIT_PHASE1"] = int(alg["time_limit_phase1"])
    if "time_limit_phase2" in alg:
        CONFIG["TIME_LIMIT_PHASE2"] = int(alg["time_limit_phase2"])
    if "max_extra_days" in alg:
        CONFIG["MAX_EXTRA_DAYS"] = int(alg["max_extra_days"])

    if alg.get("tatil_gunleri"):
        holidays = set()
        for line in alg["tatil_gunleri"].splitlines():
            line = line.strip()
            if line:
                try:
                    holidays.add(datetime.fromisoformat(line).date())
                except ValueError:
                    pass
        CONFIG["HOLIDAYS"] = holidays

    # Ders ayarlarini aktif sinava gore JSON'dan yukle
    aktif_sinav = aktif_sinav_cfg
    try:
        _daj = DersAyarlariJSON.objects.get(sinav=aktif_sinav)
        _veri = _daj.veri or {}
    except DersAyarlariJSON.DoesNotExist:
        _veri = {}

    yapilmayacak = _veri.get("yapilmayacak", [])
    if yapilmayacak:
        CONFIG["SINAV_YAPILMAYACAK_DERSLER"] = yapilmayacak
    cift_oturumlu = _veri.get("cift_oturumlu", [])
    if cift_oturumlu:
        CONFIG["CIFT_OTURUMLU_DERSLER"] = cift_oturumlu
    CONFIG["SABIT_SINAVLAR"] = [
        {
            "ders":      s["ders_adi"],
            "tarih":     s["tarih"],
            "saat":      s["saat"],
            "seviyeler": [int(v) for v in (s.get("seviyeler") or []) if str(v).isdigit()],
        }
        for s in _veri.get("sabit_sinavlar", [])
    ]
    CONFIG["SEVIYE_CATISMA_GRUPLARI"] = [
        g["dersler"] if isinstance(g.get("dersler"), list)
        else [d.strip() for d in g.get("dersler", "").split(",") if d.strip()]
        for g in _veri.get("catisma_gruplari", [])
    ]
    CONFIG["AYNI_SLOT_ESLEME"] = [
        [e["ders1"], e["ders2"]]
        for e in _veri.get("ayni_slot_esleme", [])
    ]


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


def _db_ozeti():
    from sinav.models import SubeDers, Takvim, OturmaPlani
    aktif = _aktif_sinav()
    return {
        "ogrenci":      OgrenciModel.objects.count(),
        "ders_program": DersProgrami.objects.count(),
        "sube_ders":    SubeDers.objects.count(),
        "takvim":       Takvim.objects.filter(sinav=aktif).count(),
        "oturma_plani": OturmaPlani.objects.filter(sinav=aktif).count(),
    }


def _sinav_cikti_dir(sinav=None) -> Path:
    """Aktif (ya da verilen) sınavın çıktı klasörünü döndürür."""
    base = Path(settings.MEDIA_ROOT) / "cikti"
    s = sinav or _aktif_sinav()
    if s:
        return base / f"sinav_{s.pk}"
    return base


def _cikti_dosyalari(alt_klasor=None, sinav=None):
    """
    alt_klasor: None (hepsi), 'salon', 'raporlar', 'kok' (sadece kök)
    sinav: None → aktif sınav kullanılır
    """
    cikti_root = Path(settings.MEDIA_ROOT) / "cikti"
    sinav_dir  = _sinav_cikti_dir(sinav)
    dosyalar   = []

    if alt_klasor == "salon":
        hedefler = [sinav_dir / "salon"]
    elif alt_klasor == "raporlar":
        hedefler = [sinav_dir / "raporlar"]
    elif alt_klasor == "kok":
        hedefler = [sinav_dir]
    else:
        hedefler = [sinav_dir, sinav_dir / "salon", sinav_dir / "raporlar"]

    for d in hedefler:
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in {".xlsx", ".xls"} and f.is_file():
                    rel = f.relative_to(cikti_root)
                    dosyalar.append({"ad": f.name, "rel": str(rel)})
    return dosyalar


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
        }
    return AlgoritmaForm(initial=initial)


# ---------------------------------------------------------------
# Ana sayfa – dashboard
# ---------------------------------------------------------------
def index(request):
    # Aktif sinav yoksa en yenisini otomatik aktif yap
    aktif = _aktif_sinav()
    if aktif is None:
        yeni = SinavBilgisi.objects.first()
        if yeni:
            yeni.aktif_yap()
            aktif = yeni

    kurulum = _kurulum_durumu()
    db = _db_ozeti()
    dosya = _dosya_durumu(request)
    return render(request, "sinav/index.html", {
        "aktif_sinav":   aktif,
        "sinav_listesi": SinavBilgisi.objects.all(),
        "db_ozeti":      db,
        "ciktilar":      _cikti_dosyalari(),
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
    _apply_config(request.session.get("ortaksinav_config", {}))
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


@login_required
def gozetmen_ozet(request):
    """Aktif TakvimUretim'deki tüm gözetmenler + Sınıf Listesi PDF öğretmenlerini listeler."""
    from sinav.services.ders_sinav_eslestir import tum_siniflistesi_eslestir

    aktif_sinav  = SinavBilgisi.objects.filter(aktif=True).first()
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
        if aktif_sinav else None
    )

    gozetmenler = []
    siniflistesi_map: dict = {}

    if aktif_uretim:
        # Gözetmen listesi + slot sayıları
        rows = (
            OturmaPlani.objects
            .filter(uretim=aktif_uretim)
            .exclude(gozetmen__isnull=True)
            .exclude(gozetmen="")
            .values_list("gozetmen", flat=True)
            .distinct()
            .order_by("gozetmen")
        )
        gozetmen_slot_sayisi = {}
        for ad in rows:
            gozetmen_slot_sayisi[ad] = (
                OturmaPlani.objects
                .filter(uretim=aktif_uretim, gozetmen__iexact=ad)
                .values("tarih", "saat", "oturum")
                .distinct()
                .count()
            )

        # Sınıf Listesi PDF: dp_saat = saat - 50dk ile eşleşen tüm öğretmenler
        siniflistesi_map = tum_siniflistesi_eslestir(aktif_uretim, dp_offset_dk=-50)

        # Tüm adları birleştir (gozetmen + siniflistesi sahibi)
        tum_adlar = sorted(set(gozetmen_slot_sayisi) | set(siniflistesi_map))
        for ad in tum_adlar:
            gozetmenler.append({
                "ad":               ad,
                "slot_sayisi":      gozetmen_slot_sayisi.get(ad, 0),
                "siniflistesi_adet": len(siniflistesi_map.get(ad, [])),
            })

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
    son_uretim = TakvimUretim.objects.filter(sinav=aktif).first() if aktif else None
    takvim_sayisi = Takvim.objects.filter(sinav=aktif).count()
    return {
        "aktif_sinav":       aktif,
        "alg_form":          alg_form,
        "alg_acik":          bool(alg_form.errors),
        "sube_ders_sayisi":  SubeDers.objects.count(),
        "takvim_sayisi":     takvim_sayisi,
        "onizleme_mevcut":   bool(son_uretim and son_uretim.onizleme_verisi is not None),
    }


def takvim_sayfasi(request):
    return render(request, "sinav/takvim.html", _takvim_ctx(request))


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
                "Ders":    t.ders.ders_adi if t.ders else "",
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
    from datetime import datetime as dt
    from okul.models import DersHavuzu
    from sinav.models import Takvim as TakvimModel, TakvimUretim
    aktif_sinav = _aktif_sinav()
    uretim = TakvimUretim.objects.filter(sinav=aktif_sinav).order_by("-uretim_tarihi").first()
    if not uretim or uretim.onizleme_verisi is None:
        messages.error(request, "Önizleme verisi bulunamadı.")
        return redirect("sinav:takvim_sayfasi")
    kayitlar = uretim.onizleme_verisi
    # Takvim.ders FK için ders adı → DersHavuzu eşlemesi
    # Çift oturumlu dersler " (Yazili)"/" (Uygulama)" ekiyle gelir; base adı dene.
    ders_map = {d.ders_adi: d for d in DersHavuzu.objects.all()}

    def _ders_fk(ders_adi_str):
        obj = ders_map.get(ders_adi_str)
        if obj is None:
            base = ders_adi_str.rsplit(" (", 1)[0].strip()
            obj = ders_map.get(base)
        return obj

    def _sinav_turu(ders_adi_str):
        if ders_adi_str.endswith(" (Uygulama)"):
            return "Uygulama"
        if ders_adi_str.endswith(" (Yazili)"):
            return "Yazili"
        return ""

    # Takvim.ders_saati FK için saat string → DersSaatleri eşlemesi
    from okul.models import DersSaatleri as _DS
    saatler_map = {
        str(ds.derssaati_baslangic)[:5]: ds
        for ds in _DS.objects.all()
    }

    # Yalnızca bu uretim'e ait eski Takvim kayıtlarını temizle (yeniden onaylama durumu)
    TakvimModel.objects.filter(uretim=uretim).delete()
    TakvimModel.objects.bulk_create([
        TakvimModel(
            sinav      = aktif_sinav,
            uretim     = uretim,
            tarih      = dt.strptime(r["Tarih"], "%Y-%m-%d").date(),
            saat       = r["Saat"],
            ders_saati = saatler_map.get(r["Saat"]),
            oturum     = int(r["Oturum"]),
            ders       = _ders_fk(r["Ders"]),
            sinav_turu = _sinav_turu(r["Ders"]),
            subeler    = r["Subeler"],
        )
        for r in kayitlar
    ])
    # Önizleme verisini temizle
    uretim.onizleme_verisi = None
    uretim.save(update_fields=["onizleme_verisi"])
    messages.success(request, f"Takvim onaylandı: {len(kayitlar)} kayıt DB'ye kaydedildi.")
    from_param = request.POST.get("from", "")
    from django.urls import reverse
    url = reverse("sinav:takvim_onizleme") + (f"?from={from_param}" if from_param else "")
    return redirect(url)


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
    from collections import defaultdict
    gun_map = defaultdict(list)
    for t in TakvimModel.objects.filter(uretim=aktif_uretim).order_by("tarih", "saat"):
        gun_map[t.tarih].append(t)

    for gun_kayitlari in gun_map.values():
        slot_to_oturum: dict = {}
        oturum_no = 1
        for t in gun_kayitlari:
            if t.saat not in slot_to_oturum:
                slot_to_oturum[t.saat] = oturum_no
                oturum_no += 1
            t.oturum = slot_to_oturum[t.saat]
            t.save(update_fields=["oturum"])

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
def takvim_gecmisi(request):
    """Üretilen takvimlerin listesi: hangi sınav, ne zaman, algoritma çıktısı."""
    from sinav.models import TakvimUretim
    from django.db.models import Count
    aktif = _aktif_sinav()
    kayitlar = (
        TakvimUretim.objects
        .select_related("sinav")
        .annotate(sinav_takvim_sayisi=Count("takvimler_uretim"))
        .order_by("-uretim_tarihi")
    )
    aktif_uretim = (
        TakvimUretim.objects.filter(sinav=aktif, aktif=True).first()
        if aktif else None
    )
    return render(request, "sinav/takvim_gecmisi.html", {
        "kayitlar": kayitlar,
        "aktif_uretim": aktif_uretim,
    })


def pdf_rapor(request):
    """PDF rapor üretim sayfası: seçili TakvimUretim'e bağlı takvim verilerini gösterir."""
    from sinav.models import TakvimUretim, Takvim, OturmaUretim
    from collections import defaultdict

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
        _apply_config(session_cfg)
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


def oturma_plani_pdf_view(request):
    """OturmaPlani DB'den Oturma Planı PDF'ini anlık üretip döner."""
    import io, re as _re
    from datetime import datetime as _dt
    from sinav.models import OturmaPlani, OturmaUretim
    from ortaksinav_engine.services.pdf_rapor import oturum_plani_pdf

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


def sinav_takvimi_pdf_view(request):
    """Aktif TakvimUretim'e bağlı tek sayfalık öğrenci Sınav Takvimi PDF'i döner."""
    import io
    from sinav.models import TakvimUretim
    from ortaksinav_engine.services.pdf_rapor import sinav_takvimi_pdf

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
    sinav_takvimi_pdf(buf, okul, aktif_uretim)
    buf.seek(0)
    fname = f"Sinav_Takvimi_{aktif.egitim_ogretim_yili}.pdf"
    return HttpResponse(buf.read(), content_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})


def sinif_listesi_pdf_view(request):
    """OturmaPlani DB'den Sınıf Listesi PDF'ini anlık üretip döner."""
    import io
    from datetime import datetime as _dt
    from sinav.models import OturmaPlani, OturmaUretim
    from ortaksinav_engine.services.pdf_rapor import sinif_raporu_pdf

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
        _apply_config(session_cfg)
        _log(task_id, f"> {label} baslatildi...")

        if func_name == "takvim":
            from ortaksinav_engine.services.takvim import TakvimService

            def _cancel_fn():
                with _TASKS_LOCK:
                    return _TASKS.get(task_id, {}).get("cancel", False)

            svc = TakvimService(CONFIG, log_fn=lambda m: _log(task_id, m), cancel_fn=_cancel_fn)
            svc.adim4()
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
            from sinav.models import TakvimUretim, SinavBilgisi as _SB
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
# Cikti dosyasi indirme
# ---------------------------------------------------------------
def indir_dosya(request, rel_yol: str):
    cikti_dir = Path(settings.MEDIA_ROOT) / "cikti"
    candidate = (cikti_dir / rel_yol).resolve()
    if not str(candidate).startswith(str(cikti_dir.resolve())):
        raise Http404
    if candidate.exists() and candidate.is_file():
        inline = candidate.suffix.lower() == ".pdf"
        return FileResponse(
            open(candidate, "rb"),
            as_attachment=not inline,
            filename=candidate.name,
        )
    raise Http404("Dosya bulunamadi")


# ---------------------------------------------------------------
# Sinav Bilgisi CRUD
# ---------------------------------------------------------------
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
    liste_formlar = [(s, SinavBilgisiForm(instance=s)) for s in liste]
    dosya = _dosya_durumu(request)

    return render(request, "sinav/sinav_bilgisi.html", {
        "form":          form,
        "liste_formlar": liste_formlar,
        "aktif_sinav":   _aktif_sinav(),
        "okul":          okul,
        "okul_tamam":    okul_tamam,
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


def ders_ayarlari(request):
    from okul.models import DersHavuzu
    aktif = _aktif_sinav()
    veri = _get_ayarlar(aktif)

    dp_dersler = list(DersHavuzu.objects.order_by("ders_adi"))
    tum_dersler = sorted(DersHavuzu.objects.values_list("ders_adi", flat=True))

    catisma_gruplari = veri.get("catisma_gruplari", [])
    esleme_ciftleri  = veri.get("ayni_slot_esleme", [])
    sabit_raw        = veri.get("sabit_sinavlar", [])

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

    _save_ayarlar(aktif, veri)

    # Otomatik: SubeDers yenile
    session_cfg = dict(request.session.get("ortaksinav_config", {}))
    _apply_config(session_cfg)
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

    if okulno:
        if not aktif_uretim:
            hata = "Aktif sınav takvimi bulunamadı."
        else:
            sonuclar = list(
                OturmaPlani.objects
                .filter(uretim=aktif_uretim, okulno=okulno)
                .order_by("tarih", "saat", "oturum")
                .values("tarih", "saat", "salon", "sira_no", "ders_adi", "sinifsube", "adi_soyadi")
            )
            if not sonuclar:
                hata = f"'{okulno}' okul numarasına ait kayıt bulunamadı."

    return render(request, "sinav/ogrenci_sinav_yeri.html", {
        "aktif_sinav":  aktif_sinav,
        "aktif_uretim": aktif_uretim,
        "okulno":       okulno,
        "sonuclar":     sonuclar,
        "hata":         hata,
    })
