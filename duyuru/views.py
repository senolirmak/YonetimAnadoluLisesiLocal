from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import DeleteView, UpdateView

from dersprogrami.models import DersProgrami
from nobet.models import NobetGecmisi
from nobet.views import is_yonetici, yonetici_required
from utility.constants import WEEKDAY_TO_DB as _WEEKDAY_TO_DB

from .forms import DuyuruForm
from .models import Duyuru


class YoneticiMixin(LoginRequiredMixin):
    """
    Kullanıcının yönetici gruplarından birinde olup olmadığını kontrol eder.
    (mudur_yardimcisi, okul_muduru, rehber_ogretmen, disiplin_kurulu)
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not is_yonetici(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class DuyuruSahibiMixin:
    """
    Kullanıcının, işlem yaptığı duyurunun sahibi olup olmadığını kontrol eder.
    Superuser bu kısıtlamadan muaftır.
    """

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if (
            obj.olusturan is not None
            and obj.olusturan != request.user
            and not request.user.is_superuser
        ):
            raise PermissionDenied(
                "Bu duyuruyu düzenleme veya silme yetkiniz yok, çünkü siz oluşturmadınız."
            )
        return super().dispatch(request, *args, **kwargs)


@yonetici_required
def duyuru_listesi(request):
    duyurular = Duyuru.objects.select_related("sinif", "olusturan").order_by(
        "-tarih", "-ders_saati"
    )

    # --- Ders Bilgilerini Toplu Çekme ---
    # 1. Gerekli anahtarları topla
    ders_programi_keys = set()
    atama_keys = set()
    for duyuru in duyurular:
        day_of_week = _WEEKDAY_TO_DB.get(duyuru.tarih.weekday())
        if day_of_week:
            ders_programi_keys.add((duyuru.sinif_id, day_of_week, duyuru.ders_saati))
        atama_keys.add((str(duyuru.sinif), duyuru.tarih, duyuru.ders_saati))

    # 2. Toplu sorguları yap
    # Ders Programı (Birden fazla öğretmen olabilir)
    program_q_objects = Q()
    for sinif_id, gun, ders_saati in ders_programi_keys:
        program_q_objects |= Q(sinif_sube_id=sinif_id, gun=gun, ders_saati=ders_saati)

    ders_programlari = defaultdict(list)
    if program_q_objects:
        program_results = DersProgrami.objects.filter(program_q_objects).select_related(
            "ogretmen", "sinif_sube"
        )
        for dp in program_results:
            ders_programlari[(dp.sinif_sube_id, dp.gun, dp.ders_saati)].append(dp)

    # Nöbetçi Atamaları
    atama_q_objects = Q()
    for sinif_str, tarih, ders_saati in atama_keys:
        atama_q_objects |= Q(sinif=sinif_str, tarih__date=tarih, saat=ders_saati)

    atamalar = {}
    if atama_q_objects:
        atama_results = NobetGecmisi.objects.filter(atama_q_objects).select_related(
            "ogretmen__personel"
        )
        for atama in atama_results:
            atamalar[(atama.sinif, atama.tarih.date(), atama.saat)] = atama

    # 3. Bilgileri duyuru nesnelerine ekle
    for duyuru in duyurular:
        ders_bilgisi = {"ders_adi": None, "ogretmen_adi": None, "nobetci_adi": None}

        day_of_week = _WEEKDAY_TO_DB.get(duyuru.tarih.weekday())
        program_key = (duyuru.sinif_id, day_of_week, duyuru.ders_saati)
        ders_programi_list = ders_programlari.get(program_key)

        if ders_programi_list:
            ders_adlari = sorted(
                list(set([dp.ders_adi for dp in ders_programi_list if dp.ders_adi]))
            )
            ogretmen_adlari = sorted(
                list(set([dp.ogretmen.adi_soyadi for dp in ders_programi_list if dp.ogretmen]))
            )
            ders_bilgisi["ders_adi"] = " / ".join(ders_adlari)
            ders_bilgisi["ogretmen_adi"] = ", ".join(ogretmen_adlari)

        atama_key = (str(duyuru.sinif), duyuru.tarih, duyuru.ders_saati)
        atama = atamalar.get(atama_key)
        if atama:
            ders_bilgisi["nobetci_adi"] = atama.ogretmen.personel.adi_soyadi

        duyuru.ders_bilgisi = ders_bilgisi

    return render(request, "duyuru/liste.html", {"duyurular": duyurular, "title": "Duyurular"})


@yonetici_required
def duyuru_ekle(request):
    if request.method == "POST":
        form = DuyuruForm(request.POST)
        if form.is_valid():
            duyuru = form.save(commit=False)
            duyuru.olusturan = request.user
            duyuru.save()
            messages.success(request, "Duyuru başarıyla oluşturuldu.")
            return redirect("duyuru_listesi")
    else:
        form = DuyuruForm()
    return render(request, "duyuru/form.html", {"form": form, "title": "Yeni Duyuru Ekle"})


# -- API Endpoint (Akıllı tahta veya dış ekranlar için ideal) --
def aktif_duyuru_getir_api(request, sinif_id, tarih_str, ders_saati):
    """
    Belirli bir sınıf, tarih ve ders saatindeki aktif duyuruları JSON formatında döner.
    Örnek İstek: /duyuru/api/1/2026-02-23/3/
    """
    duyurular = Duyuru.objects.filter(
        sinif_id=sinif_id, tarih=tarih_str, ders_saati=ders_saati
    ).values("mesaj", "olusturulma_zaman")

    return JsonResponse({"duyurular": list(duyurular)})


class DuyuruUpdateView(YoneticiMixin, DuyuruSahibiMixin, SuccessMessageMixin, UpdateView):
    model = Duyuru
    form_class = DuyuruForm
    template_name = "duyuru/form.html"
    success_url = reverse_lazy("duyuru_listesi")
    success_message = "Duyuru başarıyla güncellendi."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Duyuru Düzenle"
        return context


class DuyuruDeleteView(YoneticiMixin, DuyuruSahibiMixin, DeleteView):
    model = Duyuru
    template_name = "duyuru/duyuru_confirm_delete.html"
    success_url = reverse_lazy("duyuru_listesi")

    def post(self, request, *args, **kwargs):
        messages.success(request, "Duyuru başarıyla silindi.")
        return super().post(request, *args, **kwargs)
