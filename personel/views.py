from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from nobet.models import NobetPersonel

from .forms import (
    KayitForm,
    OgretmenKullaniciForm,
    PersonelDuzenleForm,
    ProfilDuzenleForm,
    SifreDegistirForm,
)

# ─────────────────────────────────────────────
# Yetki yardımcıları
# ─────────────────────────────────────────────


def _is_mudur_yardimcisi(user):
    return user.is_superuser or user.groups.filter(name="mudur_yardimcisi").exists()


def mudur_yardimcisi_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not _is_mudur_yardimcisi(request.user):
            messages.error(request, "Bu işlem için yetkiniz yok.")
            return redirect("index")
        return view_func(request, *args, **kwargs)

    return wrapper


# ─────────────────────────────────────────────
# Personel CRUD
# ─────────────────────────────────────────────


@mudur_yardimcisi_required
def personel_listesi(request):
    q = request.GET.get("q", "").strip()
    brans = request.GET.get("brans", "").strip()
    gorev_tipi = request.GET.get("gorev_tipi", "").strip()

    qs = NobetPersonel.objects.select_related("user", "ogretmen").order_by("adi_soyadi")
    if q:
        qs = qs.filter(adi_soyadi__icontains=q)
    if brans:
        qs = qs.filter(brans__iexact=brans)
    if gorev_tipi:
        qs = qs.filter(gorev_tipi__iexact=gorev_tipi)

    brans_listesi = (
        NobetPersonel.objects.values_list("brans", flat=True).distinct().order_by("brans")
    )
    gorev_tipi_listesi = (
        NobetPersonel.objects.exclude(gorev_tipi__isnull=True)
        .exclude(gorev_tipi="")
        .values_list("gorev_tipi", flat=True)
        .distinct()
        .order_by("gorev_tipi")
    )

    return render(
        request,
        "personel/personel_listesi.html",
        {
            "personeller": qs,
            "toplam": qs.count(),
            "q": q,
            "secili_brans": brans,
            "secili_gorev_tipi": gorev_tipi,
            "brans_listesi": brans_listesi,
            "gorev_tipi_listesi": gorev_tipi_listesi,
        },
    )


@mudur_yardimcisi_required
def personel_duzenle(request, pk):
    personel = get_object_or_404(NobetPersonel, pk=pk)
    form = PersonelDuzenleForm(request.POST or None, instance=personel)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{personel.adi_soyadi} bilgileri güncellendi.")
        return redirect("personel_listesi")
    return render(
        request,
        "personel/personel_duzenle.html",
        {
            "personel": personel,
            "form": form,
        },
    )


@mudur_yardimcisi_required
def personel_sil(request, pk):
    personel = get_object_or_404(NobetPersonel, pk=pk)
    if request.method == "POST":
        adi = personel.adi_soyadi
        personel.delete()
        messages.success(request, f"{adi} kaydı silindi.")
        return redirect("personel_listesi")
    return render(request, "personel/personel_sil.html", {"personel": personel})


# ─────────────────────────────────────────────
# Öğretmen kullanıcı yönetimi
# ─────────────────────────────────────────────


@mudur_yardimcisi_required
def ogretmen_kullanici_listesi(request):
    personeller = NobetPersonel.objects.select_related("user").order_by("adi_soyadi")
    return render(
        request,
        "personel/ogretmen_kullanici_listesi.html",
        {
            "personeller": personeller,
        },
    )


@mudur_yardimcisi_required
def ogretmen_kullanici_olustur(request, personel_pk):
    personel = get_object_or_404(NobetPersonel, pk=personel_pk)

    if personel.user:
        messages.warning(request, f"{personel.adi_soyadi} zaten bir kullanıcıya bağlı.")
        return redirect("ogretmen_kullanici_listesi")

    parcalar = personel.adi_soyadi.strip().split()
    initial_last = parcalar[-1] if parcalar else ""
    initial_first = " ".join(parcalar[:-1]) if len(parcalar) > 1 else personel.adi_soyadi

    form = OgretmenKullaniciForm(
        request.POST or None,
        initial={
            "username": personel.kimlikno,
            "first_name": initial_first,
            "last_name": initial_last,
        },
    )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password1"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
            )
            ogretmen_grubu, _ = Group.objects.get_or_create(name="ogretmen")
            user.groups.add(ogretmen_grubu)
            personel.user = user
            personel.save()
        messages.success(request, f"{personel.adi_soyadi} için kullanıcı oluşturuldu.")
        return redirect("ogretmen_kullanici_listesi")

    return render(
        request,
        "personel/ogretmen_kullanici_olustur.html",
        {
            "personel": personel,
            "form": form,
        },
    )


@mudur_yardimcisi_required
def ogretmen_kullanici_kaldir(request, personel_pk):
    personel = get_object_or_404(NobetPersonel, pk=personel_pk)
    if request.method == "POST":
        if personel.user:
            personel.user.delete()
            messages.success(request, f"{personel.adi_soyadi} kullanıcısı silindi.")
        return redirect("ogretmen_kullanici_listesi")
    return render(request, "personel/ogretmen_kullanici_kaldir.html", {"personel": personel})


# ─────────────────────────────────────────────
# Kayıt ve profil
# ─────────────────────────────────────────────


def tc_sorgula(request):
    """TC kimlik no ile personel kaydını AJAX ile sorgular."""
    tc = request.GET.get("tc", "").strip()
    if not tc:
        return JsonResponse({"status": "error", "message": "TC kimlik no giriniz."})
    try:
        personel = NobetPersonel.objects.get(kimlikno=tc)
    except NobetPersonel.DoesNotExist:
        return JsonResponse({"status": "not_found"})
    if personel.user:
        return JsonResponse({"status": "has_user"})
    return JsonResponse(
        {
            "status": "ok",
            "adi_soyadi": personel.adi_soyadi,
            "brans": personel.brans,
            "cinsiyet": "Erkek" if personel.cinsiyet else "Kadın",
            "suggested_username": tc,
        }
    )


def kayit(request):
    """TC kimlik no üzerinden personel eşlemeli yeni kullanıcı kaydı."""
    if request.user.is_authenticated:
        return redirect("index")

    form = KayitForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        tc = form.cleaned_data["tckimlikno"]
        personel = NobetPersonel.objects.get(kimlikno=tc)
        parcalar = personel.adi_soyadi.strip().split()
        first_name = " ".join(parcalar[:-1]) if len(parcalar) > 1 else personel.adi_soyadi
        last_name = parcalar[-1] if parcalar else ""
        with transaction.atomic():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password1"],
                first_name=first_name,
                last_name=last_name,
            )
            ogretmen_grubu, _ = Group.objects.get_or_create(name="ogretmen")
            user.groups.add(ogretmen_grubu)
            personel.user = user
            personel.save()
        messages.success(request, "Hesabınız oluşturuldu. Giriş yapabilirsiniz.")
        return redirect("login")

    return render(request, "registration/kayit.html", {"form": form})


@login_required
def profil(request):
    """Kullanıcı profil görüntüleme ve düzenleme."""
    from django.contrib.auth import update_session_auth_hash

    user = request.user
    try:
        personel = user.personel
    except Exception:
        personel = None

    profil_form = ProfilDuzenleForm(
        initial={
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
        }
    )
    sifre_form = SifreDegistirForm(user)

    if request.method == "POST":
        if "profil_kaydet" in request.POST:
            profil_form = ProfilDuzenleForm(request.POST)
            if profil_form.is_valid():
                user.first_name = profil_form.cleaned_data["first_name"]
                user.last_name = profil_form.cleaned_data["last_name"]
                user.email = profil_form.cleaned_data.get("email") or ""
                user.save()
                messages.success(request, "Profil bilgileriniz güncellendi.")
                return redirect("profil")

        elif "sifre_degistir" in request.POST:
            sifre_form = SifreDegistirForm(user, request.POST)
            if sifre_form.is_valid():
                user.set_password(sifre_form.cleaned_data["yeni_sifre1"])
                user.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Şifreniz başarıyla değiştirildi.")
                return redirect("profil")

    return render(
        request,
        "personel/profil.html",
        {
            "profil_form": profil_form,
            "sifre_form": sifre_form,
            "personel": personel,
        },
    )
