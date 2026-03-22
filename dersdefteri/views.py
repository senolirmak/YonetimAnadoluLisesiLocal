from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from dersprogrami.models import NobetDersProgrami
from nobet.models import NobetPersonel
from utility.constants import WEEKDAY_TO_DB

from .forms import DersDefterForm
from .models import DersDefteri

YONETICI_GRUPLAR = {"mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"}


def _is_yonetici(user):
    return user.is_superuser or user.groups.filter(name__in=YONETICI_GRUPLAR).exists()


def _get_personel(user):
    """Kullanıcının NobetPersonel kaydını döner, yoksa None."""
    try:
        return user.personel
    except Exception:
        return None


# ─────────────────────────────────────────────
# Bugünkü Ders Listesi
# ─────────────────────────────────────────────


@login_required
def ders_listesi(request):
    is_yonetici = _is_yonetici(request.user)

    # Yönetici: öğretmen seçebilir
    if is_yonetici:
        tum_ogretmenler = NobetPersonel.objects.order_by("adi_soyadi")
        ogretmen_id = request.GET.get("ogretmen", "").strip()
        personel = None
        if ogretmen_id:
            try:
                personel = NobetPersonel.objects.get(pk=int(ogretmen_id))
            except (NobetPersonel.DoesNotExist, ValueError):
                pass
    else:
        tum_ogretmenler = None
        personel = _get_personel(request.user)

    today = timezone.localdate()
    tarih_str = request.GET.get("tarih", "").strip()
    if tarih_str:
        from datetime import datetime
        try:
            today = datetime.strptime(tarih_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    gun_db = WEEKDAY_TO_DB.get(today.weekday(), "Monday")

    ders_durumu = []
    if personel:
        dersler = (
            NobetDersProgrami.objects.filter(ogretmen=personel, gun=gun_db)
            .select_related("sinif_sube")
            .order_by("ders_saati")
        )
        mevcut_kayitlar = {
            k.ders_saati: k
            for k in DersDefteri.objects.filter(ogretmen=personel, tarih=today)
        }
        for ders in dersler:
            ders_durumu.append({
                "ders": ders,
                "kayit": mevcut_kayitlar.get(ders.ders_saati),
            })

    context = {
        "title": "Ders Defterim" if not is_yonetici else "Ders Defteri",
        "is_yonetici": is_yonetici,
        "tum_ogretmenler": tum_ogretmenler,
        "personel": personel,
        "secilen_ogretmen_id": str(personel.pk) if personel else "",
        "today": today,
        "today_str": today.strftime("%Y-%m-%d"),
        "ders_durumu": ders_durumu,
    }
    return render(request, "dersdefteri/ders_listesi.html", context)


# ─────────────────────────────────────────────
# Kayıt Formu (Oluştur / Güncelle)
# ─────────────────────────────────────────────


@login_required
def kayit_form(request, dp_pk):
    is_yonetici = _is_yonetici(request.user)
    personel = _get_personel(request.user)

    if not personel and not is_yonetici:
        raise PermissionDenied

    dp = get_object_or_404(NobetDersProgrami, pk=dp_pk)

    # Öğretmen sadece kendi dersine erişebilir
    if not is_yonetici and dp.ogretmen != personel:
        raise PermissionDenied

    # Yönetici ise dp'nin öğretmenini kullan
    kayit_personel = dp.ogretmen

    tarih_str = request.GET.get("tarih", "").strip()
    today = timezone.localdate()
    if tarih_str:
        from datetime import datetime
        try:
            today = datetime.strptime(tarih_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    # Mevcut kayıt varsa getir, yoksa varsayılanlarla başlat
    try:
        instance = DersDefteri.objects.get(
            ogretmen=kayit_personel,
            tarih=today,
            sinif_sube=dp.sinif_sube,
            ders_saati=dp.ders_saati,
        )
    except DersDefteri.DoesNotExist:
        instance = DersDefteri(
            ogretmen=kayit_personel,
            tarih=today,
            sinif_sube=dp.sinif_sube,
            ders_adi=dp.ders_adi,
            ders_saati=dp.ders_saati,
            giris_saat=dp.giris_saat,
            cikis_saat=dp.cikis_saat,
        )

    # Yoklama verisinden devamsız öğrencileri çek
    from devamsizlik.models import OgrenciDevamsizlik
    devamsiz_qs = OgrenciDevamsizlik.objects.none()
    if dp.sinif_sube:
        from django.db.models import IntegerField
        from django.db.models.functions import Cast
        devamsiz_qs = (
            OgrenciDevamsizlik.objects.filter(
                tarih=today,
                ders_saati=dp.ders_saati,
                ogrenci__sinif=dp.sinif_sube.sinif,
                ogrenci__sube=dp.sinif_sube.sube,
            )
            .select_related("ogrenci")
            .annotate(okulno_int=Cast("ogrenci__okulno", IntegerField()))
            .order_by("okulno_int")
        )

    form = DersDefterForm(request.POST or None, instance=instance)

    if request.method == "POST" and form.is_valid():
        kayit = form.save(commit=False)
        if not kayit.pk:
            kayit.ogretmen = kayit_personel
            kayit.tarih = today
            kayit.sinif_sube = dp.sinif_sube
            kayit.ders_adi = dp.ders_adi
            kayit.ders_saati = dp.ders_saati
            kayit.giris_saat = dp.giris_saat
            kayit.cikis_saat = dp.cikis_saat
        kayit.save()
        # Yoklama verisinden devamsız öğrencileri M2M'e yaz
        devamsiz_ogrenci_ids = devamsiz_qs.values_list("ogrenci_id", flat=True)
        kayit.devamsiz_ogrenciler.set(devamsiz_ogrenci_ids)
        messages.success(request, "Ders kaydı başarıyla kaydedildi.")
        redirect_url = f"{request.path}?tarih={today.strftime('%Y-%m-%d')}"
        return redirect(redirect_url)

    context = {
        "title": "Ders Kaydı",
        "dp": dp,
        "instance": instance,
        "form": form,
        "today": today,
        "today_str": today.strftime("%Y-%m-%d"),
        "devamsiz_listesi": list(devamsiz_qs),
        "is_yonetici": is_yonetici,
    }
    return render(request, "dersdefteri/kayit_form.html", context)


# ─────────────────────────────────────────────
# Geçmiş Kayıtlar
# ─────────────────────────────────────────────


@login_required
def gecmis_listesi(request):
    is_yonetici = _is_yonetici(request.user)

    if is_yonetici:
        tum_ogretmenler = NobetPersonel.objects.order_by("adi_soyadi")
        ogretmen_id = request.GET.get("ogretmen", "").strip()
        personel = None
        if ogretmen_id:
            try:
                personel = NobetPersonel.objects.get(pk=int(ogretmen_id))
            except (NobetPersonel.DoesNotExist, ValueError):
                pass
        qs = DersDefteri.objects.select_related("ogretmen", "sinif_sube")
        if personel:
            qs = qs.filter(ogretmen=personel)
    else:
        tum_ogretmenler = None
        personel = _get_personel(request.user)
        if not personel:
            raise PermissionDenied
        qs = DersDefteri.objects.filter(ogretmen=personel).select_related("sinif_sube")

    # Tarih filtresi
    tarih_str = request.GET.get("tarih", "").strip()
    secilen_tarih = None
    if tarih_str:
        from datetime import datetime
        try:
            secilen_tarih = datetime.strptime(tarih_str, "%Y-%m-%d").date()
            qs = qs.filter(tarih=secilen_tarih)
        except ValueError:
            pass

    kayitlar = qs.prefetch_related("devamsiz_ogrenciler").order_by("-tarih", "ders_saati")

    context = {
        "title": "Geçmiş Ders Kayıtları",
        "is_yonetici": is_yonetici,
        "tum_ogretmenler": tum_ogretmenler,
        "personel": personel,
        "secilen_ogretmen_id": str(personel.pk) if personel else "",
        "kayitlar": kayitlar,
        "secilen_tarih_str": tarih_str,
    }
    return render(request, "dersdefteri/gecmis_listesi.html", context)
