from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from kurul.forms import KurulYapiFormu, UyeEkleForm
from kurul.models import Kurul, KurulTuru, KurulUyesi
from kurul.services.katalog import katalog_bossa_yukle
from kurul.services.kurulum import acilmamis_turler, yil_kurulumu
from kurul.services.pdf_rapor import gorevlendirme_listesi_pdf
from kurul.services.toplanti import personel_toplantilari
from kurul.services.uyelik import (
    gorev_yuku,
    onerilen_baskan,
    otomatik_aday_personel,
    otomatik_uyeleri_uygula,
    personel_uyelikleri,
    uye_ekle,
    yapi_doluluk,
    yapiyi_kaydet,
)
from okul.auth import mudur_yardimcisi_required
from okul.utils import get_aktif_egitim_yili


def _yil_gerekli(request):
    yil = get_aktif_egitim_yili()
    if yil is None:
        messages.error(request, "Aktif eğitim-öğretim yılı tanımlı değil; Okul Bilgisi'nden seçin.")
    return yil


@mudur_yardimcisi_required
def index(request):
    if katalog_bossa_yukle():
        messages.info(request, "Varsayılan kurul ve komisyon kataloğu yüklendi.")
    yil = get_aktif_egitim_yili()
    turler = list(KurulTuru.objects.filter(aktif=True).prefetch_related("yapi"))
    kurul_sayilari = {}
    doluluk = {}
    if yil:
        for kurul in Kurul.objects.filter(egitim_yili=yil).select_related("tur"):
            d = yapi_doluluk(kurul)
            t = doluluk.setdefault(kurul.tur_id, {"dolu": 0, "gereken": 0})
            t["dolu"] += d["dolu"]
            t["gereken"] += d["gereken"]
        for satir in (
            Kurul.objects.filter(egitim_yili=yil).values("tur")
            .annotate(kurul=Count("id", distinct=True), uye=Count("uyeler"),
                      baskan=Count("uyeler", filter=Q(uyeler__gorev=KurulUyesi.GOREV_BASKAN)))
        ):
            kurul_sayilari[satir["tur"]] = satir
    cogul = {KurulTuru.KATEGORI_KURUL: "Kurullar", KurulTuru.KATEGORI_KOMISYON: "Komisyonlar",
             KurulTuru.KATEGORI_EKIP: "Ekipler"}
    gruplar = {ad: [] for ad in cogul.values()}
    for tur in turler:
        tur.sayilar = kurul_sayilari.get(tur.pk)
        tur.doluluk = doluluk.get(tur.pk)
        gruplar[cogul[tur.kategori]].append(tur)
    gruplar = {ad: liste for ad, liste in gruplar.items() if liste}
    eksik = list(acilmamis_turler(yil)) if yil else []
    eksik_yer = sum(d["gereken"] - d["dolu"] for d in doluluk.values())
    return render(request, "kurul/index.html", {
        "title": "Kurul ve Komisyonlar",
        "egitim_yili": yil,
        "gruplar": gruplar,
        "eksik": eksik,
        "ozet": {
            "acik_kurul": sum(s["kurul"] for s in kurul_sayilari.values()),
            "eksik_yer": eksik_yer,
            "dogrulanmamis": sum(1 for t in turler if not t.son_dogrulama),
        },
    })


@mudur_yardimcisi_required
@require_POST
def yil_kurulumu_view(request):
    yil = _yil_gerekli(request)
    if yil:
        s = yil_kurulumu(yil)
        messages.success(
            request, f"{yil} için {s['acilan']} kurul açıldı, {s['otomatik_uye']} otomatik üye eklendi."
        )
    return redirect("kurul:index")


@mudur_yardimcisi_required
def tur_detay(request, kod):
    tur = get_object_or_404(KurulTuru, kod=kod)
    yil = get_aktif_egitim_yili()
    kurullar = []
    if yil:
        kurullar = list(
            Kurul.objects.filter(tur=tur, egitim_yili=yil).select_related("sinif_sube", "brans")
            .annotate(uye_sayisi=Count("uyeler"))
            .prefetch_related(Prefetch(
                "uyeler", queryset=KurulUyesi.objects.filter(gorev=KurulUyesi.GOREV_BASKAN)
                .select_related("personel", "ogrenci"), to_attr="baskanlar",
            ))
        )
        if tur.kapsam == KurulTuru.KAPSAM_OKUL and len(kurullar) == 1:
            return redirect("kurul:kurul_detay", pk=kurullar[0].pk)
        for k in kurullar:
            k.doluluk = yapi_doluluk(k)
            k.oneri = None if k.baskanlar else onerilen_baskan(k)
    return render(request, "kurul/tur_detay.html", {
        "title": tur.ad, "tur": tur, "egitim_yili": yil, "kurullar": kurullar,
    })


@mudur_yardimcisi_required
@require_POST
def tur_tamamla(request, kod):
    """Türün bu yılki bütün kurullarını önerilerle tamamlar (otomatik üyeler + önerilen başkan)."""
    tur = get_object_or_404(KurulTuru, kod=kod)
    yil = _yil_gerekli(request)
    if yil:
        toplam = sum(otomatik_uyeleri_uygula(k) for k in Kurul.objects.filter(tur=tur, egitim_yili=yil))
        messages.success(request, f"{tur.ad}: {toplam} üye/başkan önerilerle eklendi.")
    return redirect("kurul:tur_detay", kod=kod)


@mudur_yardimcisi_required
@require_POST
def kurul_ac(request, kod):
    """Okul geneli bir türün bu yılki kurulunu açar (zorunlu olmayan türler için)."""
    tur = get_object_or_404(KurulTuru, kod=kod, kapsam=KurulTuru.KAPSAM_OKUL)
    yil = _yil_gerekli(request)
    if not yil:
        return redirect("kurul:index")
    kurul, olustu = Kurul.objects.get_or_create(tur=tur, egitim_yili=yil)
    if olustu:
        otomatik_uyeleri_uygula(kurul)
        messages.success(request, f"{tur.ad} {yil} için açıldı.")
    return redirect("kurul:kurul_detay", pk=kurul.pk)


@mudur_yardimcisi_required
def kurul_detay(request, pk):
    kurul = get_object_or_404(Kurul.objects.select_related("tur", "egitim_yili", "sinif_sube", "brans"), pk=pk)
    form = UyeEkleForm()
    yapi_formu = KurulYapiFormu(kurul)
    if request.method == "POST":
        islem = request.POST.get("islem")
        if islem == "yapi":
            yapi_formu = KurulYapiFormu(kurul, request.POST)
            if yapi_formu.is_valid():
                try:
                    yapiyi_kaydet(kurul, yapi_formu.secimler())
                except ValidationError as exc:
                    messages.error(request, " ".join(exc.messages))
                else:
                    messages.success(request, "Kurul üyeleri kaydedildi.")
                    return redirect("kurul:kurul_detay", pk=kurul.pk)
        elif islem == "uye_ekle":
            form = UyeEkleForm(request.POST)
            if form.is_valid():
                try:
                    uye_ekle(kurul, **form.uye_alanlari())
                except ValidationError as exc:
                    messages.error(request, " ".join(exc.messages))
                else:
                    messages.success(request, "Üye eklendi.")
                    return redirect("kurul:kurul_detay", pk=kurul.pk)
        elif islem == "otomatik":
            n = otomatik_uyeleri_uygula(kurul)
            messages.success(request, f"Kurul önerilerle tamamlandı: {n} üye/başkan eklendi.")
            return redirect("kurul:kurul_detay", pk=kurul.pk)
        elif islem in ("cikar", "gorev"):
            uye = get_object_or_404(KurulUyesi, pk=request.POST.get("uye"), kurul=kurul)
            if islem == "cikar":
                uye.delete()
                messages.success(request, "Üye çıkarıldı.")
            else:
                gorev = request.POST.get("gorev")
                if gorev not in dict(KurulUyesi.GOREV_CHOICES):
                    raise Http404
                uye.gorev = gorev
                uye.asil = request.POST.get("asil") == "1"
                uye.save(update_fields=["gorev", "asil"])
                messages.success(request, "Üyenin görevi güncellendi.")
            return redirect("kurul:kurul_detay", pk=kurul.pk)

    uyeler = kurul.uyeler.select_related("personel", "ogrenci", "kalem")
    mevcut = set(uyeler.filter(personel__isnull=False).values_list("personel_id", flat=True))
    eksik_otomatik = [p for p in otomatik_aday_personel(kurul) if p.pk not in mevcut]
    baskan_onerisi = (
        None if uyeler.filter(gorev=KurulUyesi.GOREV_BASKAN).exists() else onerilen_baskan(kurul)
    )
    otomatik_kalemler = [
        {"kalem": k, "uyeler": [u for u in uyeler if u.kalem_id == k.pk]}
        for k in kurul.tur.yapi.filter(otomatik=True)
    ]
    return render(request, "kurul/kurul_detay.html", {
        "title": kurul.ad,
        "kurul": kurul,
        "yapi_formu": yapi_formu,
        "otomatik_kalemler": otomatik_kalemler,
        "ek_uyeler": [u for u in uyeler if u.kalem_id is None],
        "doluluk": yapi_doluluk(kurul),
        "form": form,
        "eksik_otomatik": eksik_otomatik,
        "baskan_onerisi": baskan_onerisi,
        "gorev_secenekleri": KurulUyesi.GOREV_CHOICES,
    })


@mudur_yardimcisi_required
def katalog(request):
    katalog_bossa_yukle()
    return render(request, "kurul/katalog.html", {
        "title": "Kurul ve Komisyon Yapıları",
        "turler": KurulTuru.objects.prefetch_related("yapi"),
    })


@mudur_yardimcisi_required
def gorev_yuku_view(request):
    yil = get_aktif_egitim_yili()
    return render(request, "kurul/gorev_yuku.html", {
        "title": "Kurul ve Komisyon Görev Dağılımı",
        "egitim_yili": yil,
        "satirlar": gorev_yuku(yil) if yil else [],
    })


@mudur_yardimcisi_required
def gorevlendirme_pdf(request):
    from okul.models import OkulBilgi

    yil = _yil_gerekli(request)
    if not yil:
        return redirect("kurul:index")
    kurullar = (
        Kurul.objects.filter(egitim_yili=yil, tur__aktif=True)
        .select_related("tur", "sinif_sube", "brans")
        .prefetch_related(Prefetch("uyeler", queryset=KurulUyesi.objects.select_related("personel", "ogrenci", "kalem")))
    )
    pdf = gorevlendirme_listesi_pdf(yil, kurullar, okul_adi=OkulBilgi.get().okul_adi or "")
    yanit = HttpResponse(pdf, content_type="application/pdf")
    yanit["Content-Disposition"] = f'inline; filename="kurul-komisyonlar-{yil}.pdf"'
    return yanit


@login_required
def gorevlerim(request):
    """Giriş yapan personelin bu yılki kurul ve komisyon üyelikleri."""
    personel = getattr(request.user, "personel", None)
    yil = get_aktif_egitim_yili()
    return render(request, "kurul/gorevlerim.html", {
        "title": "Kurul ve Komisyon Görevlerim",
        "egitim_yili": yil,
        "uyelikler": personel_uyelikleri(personel, yil),
        "toplantilar": personel_toplantilari(personel, yil),
        "personel_bagli": personel is not None,
    })
