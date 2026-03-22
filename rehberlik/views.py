from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cagri.models import OgrenciCagri
from nobet.models import NobetPersonel
from ogrenci.models import Ogrenci

from .models import Gorusme

# ─────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────


def _rehber_mi(user):
    return user.is_superuser or user.groups.filter(name="rehber_ogretmen").exists()


def _mudur_yardimcisi_mi(user):
    return user.is_superuser or user.groups.filter(name="mudur_yardimcisi").exists()


def _personel(request):
    try:
        return request.user.personel
    except Exception:
        return None


def _sinifsube_secenekleri():
    rows = Ogrenci.objects.values_list("sinif", "sube").distinct().order_by("sinif", "sube")
    return [f"{s}/{sb}" for s, sb in rows]


# ─────────────────────────────────────────────
# Görüşme Listesi
# ─────────────────────────────────────────────


@login_required
def gorusme_liste(request):
    kullanici_rehber = _rehber_mi(request.user)
    kullanici_mudur = _mudur_yardimcisi_mi(request.user)

    if not kullanici_rehber and not kullanici_mudur:
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")

    personel = _personel(request)

    from django.db.models import Q

    if kullanici_rehber and personel:
        # Rehber kendi kayıtlarını görür (gizliler dahil)
        qs = Gorusme.objects.filter(rehber=personel).select_related("ogrenci", "rehber")
    elif kullanici_mudur:
        # Müdür yardımcısı: gizli olmayanlar + kendi personel kaydıyla oluşturduğu gizliler
        if personel:
            qs = Gorusme.objects.filter(Q(gizli=False) | Q(rehber=personel)).select_related(
                "ogrenci", "rehber"
            )
        else:
            qs = Gorusme.objects.filter(gizli=False).select_related("ogrenci", "rehber")
    else:
        qs = Gorusme.objects.none()

    # GET filtreleri
    tarih_bas = request.GET.get("tarih_bas", "").strip()
    tarih_bit = request.GET.get("tarih_bit", "").strip()
    sinifsube = request.GET.get("sinifsube", "").strip()
    tur = request.GET.get("tur", "").strip()
    ogrenci_q = request.GET.get("ogrenci_q", "").strip()
    gizli_filtr = request.GET.get("gizli", "").strip()

    if tarih_bas:
        qs = qs.filter(tarih__gte=tarih_bas)
    if tarih_bit:
        qs = qs.filter(tarih__lte=tarih_bit)
    if sinifsube:
        parts = sinifsube.split("/")
        if len(parts) == 2:
            qs = qs.filter(ogrenci__sinif=parts[0], ogrenci__sube__iexact=parts[1])
    if tur:
        qs = qs.filter(tur=tur)
    if ogrenci_q:
        from django.db.models import Q

        qs = qs.filter(
            Q(ogrenci__adi__icontains=ogrenci_q)
            | Q(ogrenci__soyadi__icontains=ogrenci_q)
            | Q(ogrenci__okulno__icontains=ogrenci_q)
        )
    if kullanici_rehber and gizli_filtr in ("0", "1"):
        qs = qs.filter(gizli=(gizli_filtr == "1"))

    qs = qs.order_by("-tarih", "-olusturma_zamani")

    context = {
        "gorusmeler": qs,
        "toplam": qs.count(),
        "sinifsube_secenekleri": _sinifsube_secenekleri(),
        "tur_secenekleri": Gorusme.TUR_CHOICES,
        "filters": {
            "tarih_bas": tarih_bas,
            "tarih_bit": tarih_bit,
            "sinifsube": sinifsube,
            "tur": tur,
            "ogrenci_q": ogrenci_q,
            "gizli": gizli_filtr,
        },
        "kullanici_rehber": kullanici_rehber,
        "kullanici_mudur": kullanici_mudur,
        "personel": personel,
        "bugun": timezone.localdate(),
    }
    return render(request, "rehberlik/gorusme_liste.html", context)


# ─────────────────────────────────────────────
# Görüşme Oluştur
# ─────────────────────────────────────────────


@login_required
def gorusme_olustur(request):
    if not _rehber_mi(request.user):
        messages.error(request, "Bu sayfaya yalnızca rehber öğretmenler erişebilir.")
        return redirect("index")

    personel = _personel(request)
    if personel is None:
        messages.error(request, "Bu kullanıcıya bağlı personel kaydı bulunamadı.")
        return redirect("index")

    # Çağrısız görüşme açılamaz — önce çağrı oluşturulmalı
    cagri_id_kontrol = (
        request.GET.get("cagri_id", "").strip() or request.POST.get("cagri_id", "").strip()
    )
    if not cagri_id_kontrol:
        messages.warning(request, "Görüşme oluşturmak için önce öğrenci çağrısı oluşturun.")
        return redirect("rehberlik:cagri_olustur")

    ogrenciler = Ogrenci.objects.select_related("detay").order_by("sinif", "sube", "okulno")
    personeller = NobetPersonel.objects.all().order_by("adi_soyadi")
    sinifsube_secenekleri = _sinifsube_secenekleri()

    if request.method == "POST":
        tarih = request.POST.get("tarih", "").strip()
        tur = request.POST.get("tur", "").strip()
        konu = request.POST.get("konu", "").strip()
        aciklama = request.POST.get("aciklama", "").strip()
        sonuc = request.POST.get("sonuc", "").strip()
        takip_tarihi = request.POST.get("takip_tarihi", "").strip() or None
        gizli = request.POST.get("gizli") == "on"
        veli_adi = request.POST.get("veli", "").strip()
        veli_telefon = request.POST.get("velitelefon", "").strip()

        hatalar = []
        if not tarih:
            hatalar.append("Tarih zorunludur.")
        if not tur:
            hatalar.append("Görüşme türü zorunludur.")
        if not konu:
            hatalar.append("Konu zorunludur.")

        ogrenci = None
        gorusulen_ogretmen = None
        grup_ids = []

        if tur in ("bireysel", "veli"):
            ogrenci_id = request.POST.get("ogrenci_id", "").strip()
            if ogrenci_id:
                try:
                    ogrenci = Ogrenci.objects.get(pk=int(ogrenci_id))
                except (Ogrenci.DoesNotExist, ValueError):
                    hatalar.append("Geçersiz öğrenci seçimi.")
        elif tur == "grup":
            grup_ids = request.POST.getlist("grup_ogrenci_ids")
        elif tur == "ogretmen":
            ogretmen_id = request.POST.get("gorusulen_ogretmen_id", "").strip()
            if ogretmen_id:
                try:
                    gorusulen_ogretmen = NobetPersonel.objects.get(pk=int(ogretmen_id))
                except (NobetPersonel.DoesNotExist, ValueError):
                    hatalar.append("Geçersiz öğretmen seçimi.")

        if hatalar:
            for h in hatalar:
                messages.error(request, h)
        else:
            gorusme = Gorusme.objects.create(
                ogrenci=ogrenci,
                gorusulen_ogretmen=gorusulen_ogretmen,
                veli_adi=veli_adi if tur == "veli" else "",
                veli_telefon=veli_telefon if tur == "veli" else "",
                tarih=tarih,
                tur=tur,
                konu=konu,
                aciklama=aciklama,
                sonuc=sonuc,
                takip_tarihi=takip_tarihi,
                gizli=gizli,
                rehber=personel,
            )
            if tur == "grup" and grup_ids:
                gorusme.grup_ogrencileri.set(grup_ids)
            # Çağrıdan gelindiyse çağrıyı görüşmeye bağla ve devamsızlık kaydı oluştur
            cagri_id_post = request.POST.get("cagri_id", "").strip()
            if cagri_id_post:
                from devamsizlik.models import OgrenciDevamsizlik

                try:
                    cagri_obj = OgrenciCagri.objects.get(
                        pk=int(cagri_id_post),
                        kayit_eden=personel,
                        servis=OgrenciCagri.SERVIS_REHBERLIK,
                    )
                    cagri_obj.gorusme_rehberlik = gorusme  # type: ignore[assignment]
                    cagri_obj.save(update_fields=["gorusme_rehberlik"])
                    if cagri_obj.ogrenci and cagri_obj.ders_saati:
                        OgrenciDevamsizlik.objects.update_or_create(
                            ogrenci=cagri_obj.ogrenci,
                            tarih=cagri_obj.tarih,
                            ders_saati=cagri_obj.ders_saati,
                            defaults={
                                "ders_adi": cagri_obj.ders_adi or "Rehberlik",
                                "ogretmen_adi": personel.adi_soyadi,
                                "aciklama": "Rehberlik Servisi",
                            },
                        )
                except (OgrenciCagri.DoesNotExist, ValueError):
                    pass
            messages.success(request, "Görüşme kaydı oluşturuldu.")
            return redirect("rehberlik:gorusme_detay", pk=gorusme.pk)

    # Çağrı listesinden gelen ön-seçimler
    secili_tur = request.GET.get("tur", "").strip()
    secili_ogrenci_id = ""
    try:
        secili_ogrenci_id = str(int(request.GET.get("ogrenci_id", "")))
    except (ValueError, TypeError):
        pass
    cagri_id = ""
    try:
        cagri_id = str(int(request.GET.get("cagri_id", "")))
    except (ValueError, TypeError):
        pass

    context = {
        "gorusme": None,
        "ogrenciler": ogrenciler,
        "personeller": personeller,
        "sinifsube_secenekleri": sinifsube_secenekleri,
        "tur_secenekleri": Gorusme.TUR_CHOICES,
        "bugun": timezone.localdate().isoformat(),
        "secili_tur": secili_tur,
        "secili_ogrenci_id": secili_ogrenci_id,
        "cagri_id": cagri_id,
    }
    return render(request, "rehberlik/gorusme_form.html", context)


# ─────────────────────────────────────────────
# Görüşme Detay
# ─────────────────────────────────────────────


@login_required
def gorusme_detay(request, pk):
    gorusme = get_object_or_404(Gorusme, pk=pk)
    personel = _personel(request)
    rehber = _rehber_mi(request.user)
    mudur = _mudur_yardimcisi_mi(request.user)

    # Erişim kontrolü
    sahip = personel is not None and gorusme.rehber == personel

    if not sahip and not mudur and not rehber:
        messages.error(request, "Bu görüşmeyi görme yetkiniz yok.")
        return redirect("rehberlik:gorusme_liste")

    # Gizli kayıtlara yalnızca sahibi erişebilir
    if gorusme.gizli and not sahip:
        messages.error(request, "Bu gizli görüşme kaydına erişim yetkiniz yok.")
        return redirect("rehberlik:gorusme_liste")

    return render(
        request,
        "rehberlik/gorusme_detay.html",
        {
            "gorusme": gorusme,
            "sahip": sahip,
        },
    )


# ─────────────────────────────────────────────
# Görüşme Düzenle
# ─────────────────────────────────────────────


@login_required
def gorusme_duzenle(request, pk):
    gorusme = get_object_or_404(Gorusme, pk=pk)
    personel = _personel(request)

    if not _rehber_mi(request.user):
        messages.error(request, "Bu işlem için yetkiniz yok.")
        return redirect("rehberlik:gorusme_liste")

    if personel is None or gorusme.rehber != personel:
        messages.error(request, "Yalnızca kendi görüşmelerinizi düzenleyebilirsiniz.")
        return redirect("rehberlik:gorusme_detay", pk=pk)

    ogrenciler = Ogrenci.objects.select_related("detay").order_by("sinif", "sube", "okulno")
    personeller = NobetPersonel.objects.all().order_by("adi_soyadi")
    sinifsube_secenekleri = _sinifsube_secenekleri()

    if request.method == "POST":
        tarih = request.POST.get("tarih", "").strip()
        tur = request.POST.get("tur", "").strip()
        konu = request.POST.get("konu", "").strip()
        aciklama = request.POST.get("aciklama", "").strip()
        sonuc = request.POST.get("sonuc", "").strip()
        takip_tarihi = request.POST.get("takip_tarihi", "").strip() or None
        gizli = request.POST.get("gizli") == "on"
        veli_adi = request.POST.get("veli", "").strip()
        veli_telefon = request.POST.get("velitelefon", "").strip()

        hatalar = []
        if not tarih:
            hatalar.append("Tarih zorunludur.")
        if not tur:
            hatalar.append("Görüşme türü zorunludur.")
        if not konu:
            hatalar.append("Konu zorunludur.")

        ogrenci = None
        gorusulen_ogretmen = None
        grup_ids = []

        if tur in ("bireysel", "veli"):
            ogrenci_id = request.POST.get("ogrenci_id", "").strip()
            if ogrenci_id:
                try:
                    ogrenci = Ogrenci.objects.get(pk=int(ogrenci_id))
                except (Ogrenci.DoesNotExist, ValueError):
                    hatalar.append("Geçersiz öğrenci seçimi.")
        elif tur == "grup":
            grup_ids = request.POST.getlist("grup_ogrenci_ids")
        elif tur == "ogretmen":
            ogretmen_id = request.POST.get("gorusulen_ogretmen_id", "").strip()
            if ogretmen_id:
                try:
                    gorusulen_ogretmen = NobetPersonel.objects.get(pk=int(ogretmen_id))
                except (NobetPersonel.DoesNotExist, ValueError):
                    hatalar.append("Geçersiz öğretmen seçimi.")

        if hatalar:
            for h in hatalar:
                messages.error(request, h)
        else:
            gorusme.ogrenci = ogrenci  # type: ignore[assignment]
            gorusme.gorusulen_ogretmen = gorusulen_ogretmen  # type: ignore[assignment]
            gorusme.veli_adi = veli_adi if tur == "veli" else ""
            gorusme.veli_telefon = veli_telefon if tur == "veli" else ""
            gorusme.tarih = tarih
            gorusme.tur = tur
            gorusme.konu = konu
            gorusme.aciklama = aciklama
            gorusme.sonuc = sonuc
            gorusme.takip_tarihi = takip_tarihi
            gorusme.gizli = gizli
            gorusme.save()
            if tur == "grup":
                gorusme.grup_ogrencileri.set(grup_ids)
            else:
                gorusme.grup_ogrencileri.clear()
            messages.success(request, "Görüşme kaydı güncellendi.")
            return redirect("rehberlik:gorusme_detay", pk=gorusme.pk)

    secili_grup_ids = list(gorusme.grup_ogrencileri.values_list("pk", flat=True))
    context = {
        "gorusme": gorusme,
        "ogrenciler": ogrenciler,
        "personeller": personeller,
        "sinifsube_secenekleri": sinifsube_secenekleri,
        "tur_secenekleri": Gorusme.TUR_CHOICES,
        "bugun": timezone.localdate().isoformat(),
        "secili_ogrenci_id": gorusme.ogrenci.pk if gorusme.ogrenci else None,
        "secili_grup_ids": secili_grup_ids,
        "secili_ogretmen_id": gorusme.gorusulen_ogretmen.pk if gorusme.gorusulen_ogretmen else None,
    }
    return render(request, "rehberlik/gorusme_form.html", context)


# ─────────────────────────────────────────────
# Görüşme Sil
# ─────────────────────────────────────────────


@login_required
def gorusme_sil(request, pk):
    gorusme = get_object_or_404(Gorusme, pk=pk)
    personel = _personel(request)

    if not _rehber_mi(request.user):
        messages.error(request, "Bu işlem için yetkiniz yok.")
        return redirect("rehberlik:gorusme_liste")

    if personel is None or gorusme.rehber != personel:
        messages.error(request, "Yalnızca kendi görüşmelerinizi silebilirsiniz.")
        return redirect("rehberlik:gorusme_detay", pk=pk)

    if request.method == "POST":
        gorusme.delete()
        messages.success(request, "Görüşme kaydı silindi.")
        return redirect("rehberlik:gorusme_liste")

    return render(request, "rehberlik/gorusme_sil.html", {"gorusme": gorusme})
