import os
import tempfile
from datetime import datetime
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from okul.auth import ust_yonetici_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from okul.models import OkulBilgi
from sorumluluk.forms import (
    SorumluDersForm,
    SorumluDersKatalogForm,
    SorumluGorevMuafForm,
    SorumluOgrenciForm,
    SorumluSinavForm,
    TakvimAyarForm,
    XlsAktarForm,
)
from sorumluluk.models import (
    SALON_KAPASITESI,
    SALON_SAYISI,
    SorumluDers,
    SorumluDersHavuzu,
    SorumluDersKatalogBransOneri,
    SorumluDersKatalogOkulDersOnerisi,
    SorumluDersKatalogu,
    SorumluGorevMuafPersonel,
    SorumluGozetmen,
    SorumluKomisyonUyesi,
    SorumluOgrenci,
    SorumluOturmaPlani,
    SorumluSinav,
    SorumluSinavParametre,
    SorumluTakvim,
)
from sorumluluk.services.gorevlendirme_oneri import komisyon_birimleri, oner_gorevlendirme
from sorumluluk.services.import_service import sorumluluk_excel_aktar
from sorumluluk.services.takvim_motoru_ga import DjangoSinavTakvimiMotoruGA as DjangoSinavTakvimiMotoru
from sorumluluk.services.takvim_service import oturma_plani_olustur


# ─── Sınav CRUD ────────────────────────────────────────────────────────────────

@ust_yonetici_required
def sinav_liste(request):
    sinavlar = SorumluSinav.objects.select_related("egitim_yili").all()
    onaylanan_sinavlar = sinavlar.filter(onaylandi=True)

    secili_pk = request.GET.get("sinav")
    aktif_sinav = None
    secili_mi = False
    if secili_pk:
        aktif_sinav = onaylanan_sinavlar.filter(pk=secili_pk).first()
        secili_mi = aktif_sinav is not None
    if aktif_sinav is None:
        aktif_sinav = sinavlar.first()

    stats = {}
    if aktif_sinav:
        stats = {
            "ogrenci": SorumluOgrenci.objects.filter(sinav=aktif_sinav).count(),
            "ders":    SorumluDersHavuzu.objects.filter(sinav=aktif_sinav).count(),
            "oturum":  SorumluTakvim.objects.filter(sinav=aktif_sinav)
                           .values_list("tarih", "oturum_no").distinct().count(),
        }

    return render(request, "sorumluluk/sinav_liste.html", {
        "sinavlar": sinavlar,
        "aktif_sinav": aktif_sinav,
        "stats": stats,
        "onaylanan_sinavlar": onaylanan_sinavlar,
        "secili_mi": secili_mi,
    })


@ust_yonetici_required
def sinav_olustur(request):
    okul = OkulBilgi.get()
    initial = {}
    if okul.okul_egtyil_id:
        initial["egitim_yili"] = okul.okul_egtyil_id
    form = SorumluSinavForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        sinav = form.save()
        messages.success(request, "Sınav oluşturuldu.")
        return redirect("sorumluluk:sinav_detay", pk=sinav.pk)
    return render(request, "sorumluluk/sinav_form.html", {"form": form, "baslik": "Yeni Sorumluluk Sınavı"})


@ust_yonetici_required
def sinav_duzenle(request, pk):
    sinav = get_object_or_404(SorumluSinav, pk=pk)
    form  = SorumluSinavForm(request.POST or None, instance=sinav)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Sınav güncellendi.")
        return redirect("sorumluluk:sinav_detay", pk=pk)
    return render(request, "sorumluluk/sinav_form.html", {"form": form, "baslik": "Sınavı Düzenle", "sinav": sinav})


@ust_yonetici_required
def sinav_detay(request, pk):
    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=pk)

    # Kaydedilmiş parametreleri forma aktar (ortaksinav CONFIG benzeri pre-populate)
    try:
        parametreler = SorumluSinavParametre.objects.get(sinav=sinav)
    except SorumluSinavParametre.DoesNotExist:
        parametreler = None

    if parametreler is None:
        initial = {"baslangic_tarihi": timezone.localdate() + timezone.timedelta(days=1)}
        form = TakvimAyarForm(initial=initial, sinav=sinav)
    else:
        form = TakvimAyarForm(sinav=sinav, parametreler=parametreler)

    return render(request, "sorumluluk/sinav_detay.html", {
        "sinav": sinav,
        "form": form,
    })


@ust_yonetici_required
@require_POST
def sinav_sil(request, pk):
    sinav = get_object_or_404(SorumluSinav, pk=pk)
    if not sinav.silinebilir_mi():
        messages.error(request, f"\"{sinav.sinav_adi}\" arşivlenmiş olduğu için silinemez.")
        return redirect("sorumluluk:sinav_liste")
    sinav.delete()
    messages.success(request, "Sınav silindi.")
    return redirect("sorumluluk:sinav_liste")


@ust_yonetici_required
@require_POST
def sinav_arsivle(request, pk):
    sinav = get_object_or_404(SorumluSinav, pk=pk)
    if not sinav.arsivlenebilir_mi():
        messages.error(
            request,
            f"\"{sinav.sinav_adi}\" arşivlenemedi: sınav onaylanmış ve en az bir "
            "komisyon/gözetmen görevlendirmesi yapılmış olmalı.",
        )
        return redirect("sorumluluk:sinav_liste")
    sinav.arsivlendi = True
    sinav.arsivlenme_tarihi = timezone.now()
    sinav.save(update_fields=["arsivlendi", "arsivlenme_tarihi"])
    messages.success(request, f"\"{sinav.sinav_adi}\" arşivlendi.")
    return redirect("sorumluluk:sinav_liste")


# ─── Excel Import (sınava özgü) ────────────────────────────────────────────────

@ust_yonetici_required
def ogr_aktar(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)
    form  = XlsAktarForm(request.POST or None, request.FILES or None)
    sonuc = None
    if request.method == "POST" and form.is_valid():
        dosya = request.FILES["dosya"]
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xls") as tmp:
            for chunk in dosya.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            sonuc = sorumluluk_excel_aktar(tmp_path, sinav)
            messages.success(
                request,
                f"{sonuc['ogrenci']} öğrenci, {sonuc['ders']} ders aktarıldı.",
            )
        except Exception as e:
            messages.error(request, f"Hata: {e}")
        finally:
            os.unlink(tmp_path)
    return render(request, "sorumluluk/ogr_aktar.html", {
        "form": form, "sonuc": sonuc, "sinav": sinav,
    })


# ─── Öğrenci Listesi & CRUD ────────────────────────────────────────────────────

@ust_yonetici_required
def ogr_liste(request, sinav_pk):
    sinav     = get_object_or_404(SorumluSinav, pk=sinav_pk)
    ogrenciler = (
        SorumluOgrenci.objects
        .filter(sinav=sinav)
        .prefetch_related("dersler")
        .order_by("sinif", "sube", "adi_soyadi")
    )
    return render(request, "sorumluluk/ogr_liste.html", {
        "sinav": sinav, "ogrenciler": ogrenciler,
    })


@ust_yonetici_required
def ogr_ekle(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)
    form  = SorumluOgrenciForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ogr = form.save(commit=False)
        ogr.sinav = sinav
        try:
            ogr.save()
            messages.success(request, "Öğrenci eklendi.")
            return redirect("sorumluluk:ogr_liste", sinav_pk=sinav_pk)
        except IntegrityError:
            form.add_error("okulno", "Bu sınava ait bu okul numarasıyla bir öğrenci zaten kayıtlı.")
    return render(request, "sorumluluk/ogr_form.html", {
        "form": form, "sinav": sinav, "baslik": "Öğrenci Ekle",
    })


@ust_yonetici_required
def ogr_duzenle(request, pk):
    ogr  = get_object_or_404(SorumluOgrenci, pk=pk)
    form = SorumluOgrenciForm(request.POST or None, instance=ogr)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Öğrenci güncellendi.")
        return redirect("sorumluluk:ogr_liste", sinav_pk=ogr.sinav_id)
    return render(request, "sorumluluk/ogr_form.html", {
        "form": form, "sinav": ogr.sinav, "baslik": "Öğrenciyi Düzenle", "ogr": ogr,
    })


@ust_yonetici_required
@require_POST
def ogr_sil(request, pk):
    ogr = get_object_or_404(SorumluOgrenci, pk=pk)
    sinav_pk = ogr.sinav_id
    ogr.delete()
    messages.success(request, "Öğrenci silindi.")
    return redirect("sorumluluk:ogr_liste", sinav_pk=sinav_pk)


@ust_yonetici_required
def ogr_ders_ekle(request, ogr_pk):
    ogr  = get_object_or_404(SorumluOgrenci, pk=ogr_pk)
    form = SorumluDersForm(request.POST or None, ogr=ogr)
    if request.method == "POST" and form.is_valid():
        ders = form.save(commit=False)
        ders.ogrenci = ogr
        try:
            ders.save()
            messages.success(request, "Ders eklendi.")
            return redirect("sorumluluk:ogr_liste", sinav_pk=ogr.sinav_id)
        except IntegrityError:
            form.add_error("havuz_dersi", "Öğrenci için bu ders zaten ekli.")
    return render(request, "sorumluluk/ders_form.html", {
        "form": form, "ogr": ogr, "baslik": "Ders Ekle",
    })


@ust_yonetici_required
def ogr_ders_duzenle(request, pk):
    ders = get_object_or_404(SorumluDers, pk=pk)
    form = SorumluDersForm(request.POST or None, instance=ders, ogr=ders.ogrenci)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ders güncellendi.")
        return redirect("sorumluluk:ogr_liste", sinav_pk=ders.ogrenci.sinav_id)
    return render(request, "sorumluluk/ders_form.html", {
        "form": form, "ogr": ders.ogrenci, "baslik": "Dersi Düzenle", "ders": ders,
    })


@ust_yonetici_required
@require_POST
def ogr_ders_sil(request, pk):
    ders = get_object_or_404(SorumluDers, pk=pk)
    sinav_pk = ders.ogrenci.sinav_id
    ders.delete()
    messages.success(request, "Ders silindi.")
    return redirect("sorumluluk:ogr_liste", sinav_pk=sinav_pk)


# ─── Ders Havuzu (bilgilendirme amaçlı katalog — sınav planlamasını etkilemez) ──

@ust_yonetici_required
def havuz_liste(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)
    havuz = (
        SorumluDersKatalogu.objects.filter(sinav=sinav)
        .select_related("okul_dersi", "okul_dersi_onerisi")
        .prefetch_related("branslar", "brans_onerileri__brans")
        .order_by("ders_adi")
    )
    form = SorumluDersKatalogForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        hd = form.save(commit=False)
        hd.sinav = sinav
        try:
            hd.save()
            form.save_m2m()
            messages.success(request, "Ders katalog listesine eklendi.")
            return redirect("sorumluluk:havuz_liste", sinav_pk=sinav_pk)
        except IntegrityError:
            form.add_error("ders_adi", "Bu ders katalogda zaten kayıtlı.")

    bekleyen_brans_onerisi_var = any(hd.brans_onerileri.all() for hd in havuz)
    bekleyen_okul_dersi_onerisi_var = any(
        getattr(hd, "okul_dersi_onerisi", None) for hd in havuz
    )
    return render(request, "sorumluluk/havuz_liste.html", {
        "sinav": sinav, "havuz": havuz, "form": form,
        "bekleyen_oneri_var": bekleyen_brans_onerisi_var,
        "bekleyen_okul_dersi_onerisi_var": bekleyen_okul_dersi_onerisi_var,
    })


@ust_yonetici_required
def havuz_duzenle(request, pk):
    hd = get_object_or_404(SorumluDersKatalogu, pk=pk)
    form = SorumluDersKatalogForm(request.POST or None, instance=hd)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
            messages.success(request, "Ders güncellendi.")
            return redirect("sorumluluk:havuz_liste", sinav_pk=hd.sinav_id)
        except IntegrityError:
            form.add_error("ders_adi", "Bu ders katalogda zaten kayıtlı.")
    return render(request, "sorumluluk/havuz_form.html", {
        "form": form, "sinav": hd.sinav, "baslik": "Katalog Dersini Düzenle", "hd": hd,
    })


@ust_yonetici_required
@require_POST
def havuz_sil(request, pk):
    hd = get_object_or_404(SorumluDersKatalogu, pk=pk)
    sinav_pk = hd.sinav_id
    hd.delete()
    messages.success(request, "Ders katalogdan silindi. Sınav planlaması bundan etkilenmez.")
    return redirect("sorumluluk:havuz_liste", sinav_pk=sinav_pk)


@ust_yonetici_required
@require_POST
def havuz_brans_onerisi_onayla(request, pk):
    oneri = get_object_or_404(SorumluDersKatalogBransOneri, pk=pk)
    katalog, brans, sinav_pk = oneri.katalog, oneri.brans, oneri.katalog.sinav_id
    katalog.branslar.add(brans)
    oneri.delete()
    messages.success(request, f"\"{katalog.ders_adi}\" dersine \"{brans.ad}\" branşı eklendi.")
    return redirect("sorumluluk:havuz_liste", sinav_pk=sinav_pk)


@ust_yonetici_required
@require_POST
def havuz_brans_onerisi_reddet(request, pk):
    oneri = get_object_or_404(SorumluDersKatalogBransOneri, pk=pk)
    sinav_pk = oneri.katalog.sinav_id
    oneri.delete()
    messages.success(request, "Branş önerisi reddedildi.")
    return redirect("sorumluluk:havuz_liste", sinav_pk=sinav_pk)


@ust_yonetici_required
@require_POST
def havuz_okul_dersi_onerisi_onayla(request, pk):
    from okul.models import DersHavuzu

    oneri = get_object_or_404(SorumluDersKatalogOkulDersOnerisi, pk=pk)
    katalog, sinav_pk = oneri.katalog, oneri.katalog.sinav_id
    yeni_ders, _ = DersHavuzu.objects.get_or_create(ders_adi=katalog.ders_adi)
    katalog.okul_dersi = yeni_ders
    katalog.save(update_fields=["okul_dersi"])
    oneri.delete()
    messages.success(request, f"\"{katalog.ders_adi}\" Okul Ders Havuzu'na eklendi.")
    return redirect("sorumluluk:havuz_liste", sinav_pk=sinav_pk)


@ust_yonetici_required
@require_POST
def havuz_okul_dersi_onerisi_reddet(request, pk):
    oneri = get_object_or_404(SorumluDersKatalogOkulDersOnerisi, pk=pk)
    sinav_pk = oneri.katalog.sinav_id
    oneri.delete()
    messages.success(request, "Okul Ders Havuzu önerisi reddedildi.")
    return redirect("sorumluluk:havuz_liste", sinav_pk=sinav_pk)


# ─── Takvim ────────────────────────────────────────────────────────────────────

@ust_yonetici_required
def takvim_olustur(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)
    if sinav.onaylandi:
        messages.error(request, "Onaylanmış sınavın takvimi yeniden oluşturulamaz. Önce onayı kaldırın.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

    if request.method == "POST":
        form = TakvimAyarForm(request.POST, sinav=sinav)
        if form.is_valid():
            baslama_tarihi  = form.cleaned_data["baslangic_tarihi"]
            max_sinav       = form.cleaned_data["max_gunluk_sinav"]
            cift_oturumlu   = form.cleaned_data["cift_oturumlu_dersler"]
            cift_idler      = list(cift_oturumlu.values_list("id", flat=True))
            oturum_saatleri_str = form.cleaned_data["oturum_saatleri"]
            slot_max_ders   = form.cleaned_data["slot_max_ders"]
            max_iter        = form.cleaned_data["max_iter"]
            tatil_gunleri_str   = form.cleaned_data["tatil_gunleri"]
            exclude_weekends    = form.cleaned_data["exclude_weekends"]
            haric_ogrenciler    = form.cleaned_data.get("haric_tutulacak_ogrenciler")

            SorumluOgrenci.objects.filter(sinav=sinav).update(aktif=True)
            if haric_ogrenciler:
                haric_ogrenciler.update(aktif=False)

            time_slots  = []
            saatler_dict = {}
            for i, slot_str in enumerate(oturum_saatleri_str.split(",")):
                parts = slot_str.split("-")
                if len(parts) != 2:
                    messages.error(request, f"Oturum saati hatalı format: '{slot_str.strip()}'. Örnek: 08:50-09:30")
                    return redirect("sorumluluk:gorevlendirme", sinav_pk=sinav_pk)
                bas = parts[0].strip()
                bit = parts[1].strip()
                slot_no = i + 1
                time_slots.append(slot_no)
                saatler_dict[slot_no] = (bas, bit)

            tatil_tarihleri = []
            if tatil_gunleri_str:
                for t in tatil_gunleri_str.split(","):
                    try:
                        tatil_tarihleri.append(datetime.strptime(t.strip(), "%d.%m.%Y").date())
                    except ValueError:
                        pass

            try:
                motor = DjangoSinavTakvimiMotoru(
                    sinav, baslangic_tarihi=baslama_tarihi, time_slots=time_slots,
                    cift_oturumlu_dersler=cift_idler, tatil_tarihleri=tatil_tarihleri,
                    exclude_weekends=exclude_weekends,
                )
                en_iyi_takvim = motor.optimize_edilmis_takvim(
                    max_iter=max_iter, max_daily_exams=max_sinav, slot_max_ders=slot_max_ders
                )
                # Takvim yeniden oluşturulduğunda eski görevlendirmeler de temizlenir
                SorumluKomisyonUyesi.objects.filter(sinav=sinav).delete()
                SorumluGozetmen.objects.filter(sinav=sinav).delete()
                motor.veritabanina_kaydet(en_iyi_takvim, saatler_dict)
                oturma_plani_olustur(sinav)

                # --- Aynı dersin öğrencilerini aynı salonda grupla ---
                planlar = list(
                    SorumluOturmaPlani.objects.filter(sinav=sinav)
                    .order_by("tarih", "oturum_no", "ders_adi", "sinifsube", "adi_soyadi")
                )
                salon_isimleri = [f"Sorumluluk{i+1}" for i in range(SALON_SAYISI)]
                
                for (tarih, oturum_no), group in groupby(planlar, key=lambda x: (x.tarih, x.oturum_no)):
                    oturum_planlari = list(group)
                    
                    is_uygulama_session = any("(Uygulama)" in op.ders_adi for op in oturum_planlari)
                    
                    if is_uygulama_session:
                        import re
                        def get_gercek_ders_adi(d_adi):
                            base = d_adi.split(" (Grup ")[0] if " (Grup " in d_adi else d_adi
                            base = base.replace(" (Uygulama)", "").replace(" (Yazılı)", "")
                            m = re.search(r" \(\d+\. Sınıf\)$", base)
                            if m:
                                return base[:m.start()].strip()
                            return base.strip()
                            
                        oturum_planlari.sort(key=lambda op: get_gercek_ders_adi(op.ders_adi))
                        courses = [list(c_group) for _, c_group in groupby(oturum_planlari, key=lambda op: get_gercek_ders_adi(op.ders_adi))]
                    else:
                        courses = [list(c_group) for _, c_group in groupby(oturum_planlari, key=lambda x: x.ders_adi)]
                        
                    salon_counts = {s: 0 for s in salon_isimleri}
                    current_salon_idx = 0
                    
                    for c_students in courses:
                        c_len = len(c_students)
                        
                        # Uygulama sınavlarında her farklı ders yeni bir salonda başlamalı
                        if is_uygulama_session and salon_counts[salon_isimleri[current_salon_idx]] > 0:
                            if current_salon_idx + 1 < len(salon_isimleri):
                                current_salon_idx += 1
                                
                        current_salon = salon_isimleri[current_salon_idx]
                        
                        if salon_counts[current_salon] + c_len <= SALON_KAPASITESI:
                            # Dersi tamamen mevcut salona sığdır
                            for op in c_students:
                                op.salon = current_salon
                                salon_counts[current_salon] += 1
                                op.sira_no = salon_counts[current_salon]
                        else:
                            # Mevcut salona sığmıyorsa, bir sonraki salona geçmeyi dene
                            next_salon_idx = current_salon_idx + 1
                            if next_salon_idx < len(salon_isimleri) and c_len <= SALON_KAPASITESI:
                                current_salon_idx = next_salon_idx
                                current_salon = salon_isimleri[current_salon_idx]
                                for op in c_students:
                                    op.salon = current_salon
                                    salon_counts[current_salon] += 1
                                    op.sira_no = salon_counts[current_salon]
                            else:
                                # Diğer salona da sığmıyorsa veya tek salondan büyükse, mecburen bölerek doldur
                                for op in c_students:
                                    if salon_counts[current_salon] >= SALON_KAPASITESI and current_salon_idx + 1 < len(salon_isimleri):
                                        current_salon_idx += 1
                                        current_salon = salon_isimleri[current_salon_idx]
                                    op.salon = current_salon
                                    salon_counts[current_salon] += 1
                                    op.sira_no = salon_counts[current_salon]
                
                if planlar:
                    # Güncelleme sırasında oluşan "unique constraint" (tekil kısıtlama) hatasını 
                    # önlemek için mevcut kayıtları silip yeniden toplu olarak ekliyoruz.
                    SorumluOturmaPlani.objects.filter(sinav=sinav).delete()
                    for op in planlar:
                        op.pk = None
                    SorumluOturmaPlani.objects.bulk_create(planlar)
                # -----------------------------------------------------

                # Parametreleri kaydet — bir sonraki açılışta form pre-populate edilsin
                SorumluSinavParametre.objects.update_or_create(
                    sinav=sinav,
                    defaults={
                        "baslangic_tarihi":      baslama_tarihi,
                        "oturum_saatleri":       [s.strip() for s in oturum_saatleri_str.split(",")],
                        "max_gunluk_sinav":      max_sinav,
                        "slot_max_ders":         slot_max_ders,
                        "tatil_tarihleri":       [t.strftime("%d.%m.%Y") for t in tatil_tarihleri],
                        "hafta_sonu_haric":      exclude_weekends,
                        "cift_oturumlu_dersler": cift_idler,
                    },
                )

                messages.success(request, "Algoritma başarıyla çalıştı ve takvim oluşturuldu.")
                return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)
            except Exception as e:
                messages.error(request, f"Takvim oluşturulurken hata: {str(e)}")

        return render(request, "sorumluluk/sinav_detay.html", {"form": form, "sinav": sinav})

    return redirect("sorumluluk:sinav_detay", pk=sinav_pk)


def _get_oturumlar_veri(sinav):
    """Sınava ait takvim ve oturma planı kayıtlarını birleştirerek görünümler için ortak veri yapısı üretir."""
    takvim_rows = list(
        SorumluTakvim.objects
        .filter(sinav=sinav)
        .order_by("tarih", "oturum_no", "ders_adi")
    )

    oturma_dict = {}
    for op in SorumluOturmaPlani.objects.filter(sinav=sinav).order_by("salon", "sira_no"):
        oturma_dict.setdefault((op.tarih, op.oturum_no), []).append(op)

    oturumlar_veri = []
    for (tarih, oturum_no), rows in groupby(takvim_rows, key=lambda r: (r.tarih, r.oturum_no)):
        rows = list(rows)
        kayitlar = oturma_dict.get((tarih, oturum_no), [])
        oturumlar_veri.append({
            "tarih":          tarih,
            "oturum_no":      oturum_no,
            "saat_baslangic": rows[0].saat_baslangic,
            "saat_bitis":     rows[0].saat_bitis,
            "dersler":        [r.ders_adi for r in rows],
            "ders_sayisi":    len(rows),
            "salon1":         [k for k in kayitlar if k.salon == "Sorumluluk1"],
            "salon2":         [k for k in kayitlar if k.salon == "Sorumluluk2"],
            "salon3":         [k for k in kayitlar if k.salon == "Sorumluluk3"],
        })
    return oturumlar_veri


@ust_yonetici_required
def takvim_detay(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)

    oturumlar_veri = _get_oturumlar_veri(sinav)

    return render(request, "sorumluluk/takvim_detay.html", {
        "sinav": sinav,
        "oturumlar_veri": oturumlar_veri,
    })


@ust_yonetici_required
@require_POST
def takvim_onayla(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)
    sinav.onaylandi  = True
    sinav.onay_tarihi = timezone.now()
    sinav.save(update_fields=["onaylandi", "onay_tarihi"])
    messages.success(request, "Takvim onaylandı.")
    return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)


@ust_yonetici_required
@require_POST
def takvim_onay_iptal(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)
    sinav.onaylandi   = False
    sinav.onay_tarihi = None
    sinav.save(update_fields=["onaylandi", "onay_tarihi"])
    messages.success(request, "Onay kaldırıldı.")
    return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)


@ust_yonetici_required
def rapor(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)
    if not sinav.onaylandi:
        messages.error(request, "Rapor için önce onaylayın.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

    oturumlar_veri = _get_oturumlar_veri(sinav)

    okul = OkulBilgi.get()
    return render(request, "sorumluluk/rapor.html", {
        "sinav": sinav,
        "oturumlar_veri": oturumlar_veri,
        "okul": okul,
    })


@ust_yonetici_required
def rapor_pdf(request, sinav_pk):
    import io
    from sorumluluk.services.pdf_service import rapor_pdf_uret

    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)
    if not sinav.onaylandi:
        messages.error(request, "PDF için önce takvimi onaylamalısınız.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

    oturumlar_veri = _get_oturumlar_veri(sinav)

    okul = OkulBilgi.get()
    buf  = io.BytesIO()
    rapor_pdf_uret(buf, sinav, okul, oturumlar_veri)
    buf.seek(0)

    donem  = sinav.get_donem_turu_display()  # type: ignore[attr-defined]
    egitim = str(sinav.egitim_yili) if sinav.egitim_yili else ""
    fname  = f"Salon_Yoklama_{egitim}_{donem}.pdf".replace(" ", "_")
    return HttpResponse(
        buf.read(), content_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@ust_yonetici_required
def rapor_imza_pdf(request, sinav_pk):
    import io
    from sorumluluk.services.pdf_service import rapor_pdf_uret

    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)
    if not sinav.onaylandi:
        messages.error(request, "PDF için önce takvimi onaylamalısınız.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

    oturumlar_veri = _get_oturumlar_veri(sinav)

    okul = OkulBilgi.get()
    buf  = io.BytesIO()
    rapor_pdf_uret(buf, sinav, okul, oturumlar_veri, imza_sirkusu=True)
    buf.seek(0)

    donem  = sinav.get_donem_turu_display()  # type: ignore[attr-defined]
    egitim = str(sinav.egitim_yili) if sinav.egitim_yili else ""
    fname  = f"Ogrenci_Imza_Listesi_{egitim}_{donem}.pdf".replace(" ", "_")
    return HttpResponse(
        buf.read(), content_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )

@ust_yonetici_required
def rapor_genel_takvim_pdf(request, sinav_pk):
    import io
    from sorumluluk.services.pdf_service import genel_takvim_pdf_uret

    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)
    if not sinav.onaylandi:
        messages.error(request, "PDF için önce takvimi onaylamalısınız.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

    oturumlar_veri = _get_oturumlar_veri(sinav)

    okul = OkulBilgi.get()
    buf  = io.BytesIO()
    genel_takvim_pdf_uret(buf, sinav, okul, oturumlar_veri)
    buf.seek(0)

    donem  = sinav.get_donem_turu_display()  # type: ignore[attr-defined]
    egitim = str(sinav.egitim_yili) if sinav.egitim_yili else ""
    fname  = f"Genel_Sinav_Takvimi_{egitim}_{donem}.pdf".replace(" ", "_")
    return HttpResponse(
        buf.read(), content_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )

@ust_yonetici_required
@require_POST
def takvim_oturum_tarihi_guncelle(request, sinav_pk):
    from datetime import date as _date
    from django.db import transaction

    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)
    from datetime import time as _time

    try:
        eski_tarih = _date.fromisoformat(request.POST.get("eski_tarih", ""))
        yeni_tarih = _date.fromisoformat(request.POST.get("yeni_tarih", ""))
        oturum_no  = int(request.POST.get("oturum_no", ""))
    except (ValueError, TypeError):
        messages.error(request, "Geçersiz tarih veya oturum bilgisi.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

    def _parse_time(val):
        """HH:MM → time nesnesi, hata halinde None."""
        try:
            parts = val.strip().split(":")
            return _time(int(parts[0]), int(parts[1]))
        except Exception:
            return None

    yeni_bas = _parse_time(request.POST.get("yeni_saat_baslangic", ""))
    yeni_bit = _parse_time(request.POST.get("yeni_saat_bitis", ""))

    if yeni_tarih == eski_tarih and yeni_bas is None and yeni_bit is None:
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

    # Taşınan dersler
    eski_dersler = set(
        SorumluTakvim.objects
        .filter(sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no)
        .values_list("ders_adi", flat=True)
    )
    # Hedef slottaki mevcut dersler
    hedef_dersler = set(
        SorumluTakvim.objects
        .filter(sinav=sinav, tarih=yeni_tarih, oturum_no=oturum_no)
        .values_list("ders_adi", flat=True)
    )
    cakisan = eski_dersler & hedef_dersler
    if cakisan:
        messages.error(
            request,
            f"{yeni_tarih.strftime('%d.%m.%Y')} — Oturum {oturum_no}'de çakışan ders(ler) var: "
            f"{', '.join(sorted(cakisan))}",
        )
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

    hedef_var = bool(hedef_dersler)  # hedef slotta zaten kayıt var → merge modu

    from django.db.models import Max

    with transaction.atomic():
        # Takvim ve komisyon: ders_adi dahil unique_together, çakışma garantili değil
        SorumluTakvim.objects.filter(
            sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
        ).update(tarih=yeni_tarih)
        SorumluKomisyonUyesi.objects.filter(
            sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
        ).update(tarih=yeni_tarih)

        if hedef_var:
            # Gozetmen: hedefte zaten atanmış salonları atla
            hedef_salonlar = set(
                SorumluGozetmen.objects
                .filter(sinav=sinav, tarih=yeni_tarih, oturum_no=oturum_no)
                .values_list("salon", flat=True)
            )
            SorumluGozetmen.objects.filter(
                sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no,
                salon__in=hedef_salonlar,
            ).delete()
            SorumluGozetmen.objects.filter(
                sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
            ).update(tarih=yeni_tarih)

            # OturmaPlani: hedef salon max sira_no'dan devam et
            salon_max = dict(
                SorumluOturmaPlani.objects
                .filter(sinav=sinav, tarih=yeni_tarih, oturum_no=oturum_no)
                .values("salon")
                .annotate(m=Max("sira_no"))
                .values_list("salon", "m")
            )
            to_move = list(
                SorumluOturmaPlani.objects
                .filter(sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no)
                .order_by("salon", "sira_no")
            )
            SorumluOturmaPlani.objects.filter(
                sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
            ).delete()
            counters: dict = dict(salon_max)
            for op in to_move:
                counters[op.salon] = counters.get(op.salon, 0) + 1
                op.pk      = None
                op.tarih   = yeni_tarih
                op.sira_no = counters[op.salon]
            if to_move:
                SorumluOturmaPlani.objects.bulk_create(to_move)
        else:
            SorumluGozetmen.objects.filter(
                sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
            ).update(tarih=yeni_tarih)
            SorumluOturmaPlani.objects.filter(
                sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
            ).update(tarih=yeni_tarih)

    # Saat güncelleme — tarih işlemlerinden bağımsız, yeni_tarih üzerinden uygula
    saat_guncelleme = {}
    if yeni_bas is not None:
        saat_guncelleme["saat_baslangic"] = yeni_bas
    if yeni_bit is not None:
        saat_guncelleme["saat_bitis"] = yeni_bit

    if saat_guncelleme:
        with transaction.atomic():
            SorumluTakvim.objects.filter(
                sinav=sinav, tarih=yeni_tarih, oturum_no=oturum_no
            ).update(**saat_guncelleme)
            SorumluOturmaPlani.objects.filter(
                sinav=sinav, tarih=yeni_tarih, oturum_no=oturum_no
            ).update(**saat_guncelleme)

    mesaj_parcalari = []
    if yeni_tarih != eski_tarih:
        eylem = "birleştirildi" if hedef_var else "güncellendi"
        mesaj_parcalari.append(
            f"Tarih {eski_tarih.strftime('%d.%m.%Y')} → {yeni_tarih.strftime('%d.%m.%Y')} olarak {eylem}"
        )
    if yeni_bas is not None:
        mesaj_parcalari.append(f"Başlangıç {yeni_bas.strftime('%H:%M')}")
    if yeni_bit is not None:
        mesaj_parcalari.append(f"Bitiş {yeni_bit.strftime('%H:%M')}")

    messages.success(request, f"Oturum {oturum_no} — {', '.join(mesaj_parcalari)}.")
    return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)


# ─── Görev Muafiyeti ───────────────────────────────────────────────────────────

@ust_yonetici_required
def gorev_muaf_liste(request):
    muaf_liste = (
        SorumluGorevMuafPersonel.objects
        .select_related("personel", "personel__brans")
        .order_by("personel__adi_soyadi")
    )
    form = SorumluGorevMuafForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Personel görev muafiyeti listesine eklendi.")
        return redirect("sorumluluk:gorev_muaf_liste")
    return render(request, "sorumluluk/gorev_muaf_liste.html", {
        "muaf_liste": muaf_liste, "form": form,
    })


@ust_yonetici_required
@require_POST
def gorev_muaf_sil(request, pk):
    kayit = get_object_or_404(SorumluGorevMuafPersonel, pk=pk)
    kayit.delete()
    messages.success(request, "Muafiyet kaldırıldı.")
    return redirect("sorumluluk:gorev_muaf_liste")


@ust_yonetici_required
def gorevlendirme(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)

    takvim_rows = list(
        SorumluTakvim.objects
        .filter(sinav=sinav)
        .order_by("tarih", "oturum_no", "ders_adi")
    )

    if not takvim_rows:
        messages.error(request, "Önce sınav takvimini oluşturun.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

    # Hangi (tarih, oturum_no) çiftinde hangi salonlar aktif?
    active_salons: dict = {}
    for op in (
        SorumluOturmaPlani.objects
        .filter(sinav=sinav)
        .values("tarih", "oturum_no", "salon")
        .distinct()
    ):
        key = (op["tarih"], op["oturum_no"])
        active_salons.setdefault(key, set()).add(op["salon"])

    # Mevcut atamaları önceden yükle — anahtar takvim PK'sına değil içeriğe bağlı
    komisyon_dict = {
        (ku.tarih, ku.oturum_no, ku.ders_adi): ku
        for ku in SorumluKomisyonUyesi.objects.filter(sinav=sinav).select_related("uye1", "uye2")
    }
    gozetmen_dict = {
        (gz.tarih, gz.oturum_no, gz.salon): gz
        for gz in SorumluGozetmen.objects.filter(sinav=sinav).select_related("gozetmen")
    }

    if request.method == "POST":
        from okul.models import Personel

        muaf_ids = set(SorumluGorevMuafPersonel.objects.values_list("personel_id", flat=True))
        muaf_secim_sayisi = 0

        def get_personel(field_name):
            nonlocal muaf_secim_sayisi
            val = request.POST.get(field_name, "").strip()
            if val:
                try:
                    personel = Personel.objects.get(pk=int(val))
                except (Personel.DoesNotExist, ValueError):
                    return None
                if personel.pk in muaf_ids:
                    # Görev Muafiyeti listesindeki personele hiçbir görev (komisyon/gözetmen)
                    # verilemez — dropdown seçenekleri arasında görünmez, ama form tampering'e
                    # veya seçim yapıldıktan sonra muafiyet eklenmesine karşı sunucu tarafında
                    # da reddedilir.
                    muaf_secim_sayisi += 1
                    return None
                return personel
            return None

        for row in takvim_rows:
            SorumluKomisyonUyesi.objects.update_or_create(
                sinav=sinav, tarih=row.tarih, oturum_no=row.oturum_no, ders_adi=row.ders_adi,
                defaults={
                    "uye1": get_personel(f"komisyon_{row.pk}_uye1"),
                    "uye2": get_personel(f"komisyon_{row.pk}_uye2"),
                },
            )

        # Komisyon senkronizasyonu: aynı birime (Yazılı/Uygulama ikilisi VEYA aynı
        # slotta farklı sınıf seviyesindeki aynı ders — bkz. komisyon_birimleri())
        # ait satırlar AYNI komisyon üyelerini paylaşmalı. Kullanıcı bu satırlardan
        # birini (tam) doldurup diğerini boş/eksik bırakabilir; en TAM doldurulmuş
        # satır o birim için "doğru" kabul edilip diğer satırlara kopyalanır.
        komisyon_map_fresh = {
            (ku.tarih, ku.oturum_no, ku.ders_adi): ku
            for ku in SorumluKomisyonUyesi.objects.filter(sinav=sinav).select_related("uye1", "uye2")
        }
        for rows in komisyon_birimleri(takvim_rows):
            if len(rows) < 2:
                continue
            en_dolu_ku, en_dolu_puan = None, -1
            for row in rows:
                ku = komisyon_map_fresh.get((row.tarih, row.oturum_no, row.ders_adi))
                puan = (1 if ku and ku.uye1_id else 0) + (1 if ku and ku.uye2_id else 0)
                if puan > en_dolu_puan:
                    en_dolu_ku, en_dolu_puan = ku, puan
            if en_dolu_puan <= 0:
                continue
            for row in rows:
                ku = komisyon_map_fresh.get((row.tarih, row.oturum_no, row.ders_adi))
                if ku is None or ku.uye1_id != en_dolu_ku.uye1_id or ku.uye2_id != en_dolu_ku.uye2_id:
                    SorumluKomisyonUyesi.objects.update_or_create(
                        sinav=sinav, tarih=row.tarih, oturum_no=row.oturum_no, ders_adi=row.ders_adi,
                        defaults={"uye1": en_dolu_ku.uye1, "uye2": en_dolu_ku.uye2},
                    )

        for (tarih, oturum_no), salons in active_salons.items():
            for salon in salons:
                SorumluGozetmen.objects.update_or_create(
                    sinav=sinav, tarih=tarih, oturum_no=oturum_no, salon=salon,
                    defaults={"gozetmen": get_personel(f"gozetmen_{tarih}_{oturum_no}_{salon}")},
                )

        if muaf_secim_sayisi:
            messages.warning(
                request,
                f"{muaf_secim_sayisi} görev alanı, seçilen personel Görev Muafiyeti "
                f"listesinde olduğu için boş bırakıldı.",
            )
        messages.success(request, "Görevlendirmeler kaydedildi.")
        return redirect("sorumluluk:gorevlendirme", sinav_pk=sinav_pk)

    context = _gorevlendirme_baglam(sinav, takvim_rows, active_salons, komisyon_dict, gozetmen_dict)
    return render(request, "sorumluluk/gorevlendirme.html", context)


def _gorevlendirme_baglam(sinav, takvim_rows, active_salons, komisyon_dict, gozetmen_dict):
    """`gorevlendirme` (DB'den yüklü) ve `gorevlendirme_oner` (öneri, kaydedilmemiş)
    view'larının ortak render bağlamını üretir."""
    from okul.models import Personel as OkulPersonel
    muaf_ids = SorumluGorevMuafPersonel.objects.values_list("personel_id", flat=True)
    personel_listesi = list(
        OkulPersonel.objects.select_related("brans").exclude(pk__in=muaf_ids).order_by("adi_soyadi")
    )

    oturumlar = []
    for (tarih, oturum_no), rows in groupby(takvim_rows, key=lambda r: (r.tarih, r.oturum_no)):
        rows = list(rows)
        dersler_data = [
            {"takvim": row, "komisyon": komisyon_dict.get((row.tarih, row.oturum_no, row.ders_adi))}
            for row in rows
        ]
        salons_data = [
            {
                "salon": salon,
                "salon_label": dict(
                    [("Sorumluluk1", "Mazeret 1"), ("Sorumluluk2", "Mazeret 2"), ("Sorumluluk3", "Mazeret 3")]
                ).get(salon, salon),
                "gozetmen": gozetmen_dict.get((tarih, oturum_no, salon)),
            }
            for salon in sorted(active_salons.get((tarih, oturum_no), []))
        ]
        oturumlar.append({
            "tarih": tarih,
            "oturum_no": oturum_no,
            "saat_baslangic": rows[0].saat_baslangic,
            "saat_bitis": rows[0].saat_bitis,
            "dersler_data": dersler_data,
            "ders_sayisi": len(rows),
            "salons_data": salons_data,
        })

    # Görev sayısı özeti — tüm personel dahil, branş bazında gruplu
    gorev_sayac: dict = {p.pk: {"adi_soyadi": p.adi_soyadi, "brans": p.brans.ad if p.brans else "", "komisyon": 0, "gozetmen": 0} for p in personel_listesi}

    # Komisyon sayımı (union-find):
    #  - Aynı (tarih, oturum_no) slotundaki farklı dersler → 1 görev
    #  - Farklı slotlarda aynı ders_adi (çok günlü sınav) → 1 görev
    komisyon_kayitlar: dict = {}  # personel_pk → [(ders_adi, tarih, oturum_no), ...]
    for ku in komisyon_dict.values():
        for pid in (ku.uye1_id, ku.uye2_id):
            if pid and pid in gorev_sayac:
                komisyon_kayitlar.setdefault(pid, []).append(
                    (ku.ders_adi, ku.tarih, ku.oturum_no)
                )
    for pid, kayitlar in komisyon_kayitlar.items():
        n = len(kayitlar)
        parent = list(range(n))
        for i in range(n):
            for j in range(i + 1, n):
                d_i, t_i, o_i = kayitlar[i]
                d_j, t_j, o_j = kayitlar[j]
                if (t_i == t_j and o_i == o_j) or d_i == d_j:
                    ri, rj = i, j
                    while parent[ri] != ri:
                        ri = parent[ri]
                    while parent[rj] != rj:
                        rj = parent[rj]
                    if ri != rj:
                        parent[ri] = rj
        roots = set()
        for i in range(n):
            r = i
            while parent[r] != r:
                r = parent[r]
            roots.add(r)
        gorev_sayac[pid]["komisyon"] = len(roots)

    for gz in gozetmen_dict.values():
        if gz.gozetmen_id and gz.gozetmen_id in gorev_sayac:
            gorev_sayac[gz.gozetmen_id]["gozetmen"] += 1

    # Kümülatif görev sayısı — tüm SorumluSinav kayıtları
    kumulatif_sayac = {p.pk: {"komisyon": 0, "gozetmen": 0} for p in personel_listesi}

    kum_komisyon_kayitlar: dict = {}  # personel_pk → [(sinav_id, ders_adi, tarih, oturum_no)]
    for ku in SorumluKomisyonUyesi.objects.all():
        for pid in (ku.uye1_id, ku.uye2_id):
            if pid and pid in kumulatif_sayac:
                kum_komisyon_kayitlar.setdefault(pid, []).append(
                    (ku.sinav_id, ku.ders_adi, ku.tarih, ku.oturum_no)
                )
    for pid, kayitlar in kum_komisyon_kayitlar.items():
        n = len(kayitlar)
        parent = list(range(n))
        for i in range(n):
            for j in range(i + 1, n):
                s_i, d_i, t_i, o_i = kayitlar[i]
                s_j, d_j, t_j, o_j = kayitlar[j]
                if s_i == s_j and ((t_i == t_j and o_i == o_j) or d_i == d_j):
                    ri, rj = i, j
                    while parent[ri] != ri: ri = parent[ri]
                    while parent[rj] != rj: rj = parent[rj]
                    if ri != rj: parent[ri] = rj
        roots = set()
        for i in range(n):
            r = i
            while parent[r] != r: r = parent[r]
            roots.add(r)
        kumulatif_sayac[pid]["komisyon"] = len(roots)

    for gz in SorumluGozetmen.objects.all():
        if gz.gozetmen_id and gz.gozetmen_id in kumulatif_sayac:
            kumulatif_sayac[gz.gozetmen_id]["gozetmen"] += 1

    # Geçmiş dönem (OncekiDonemGorev) kümülatife ekle
    from sorumluluk.models import OncekiDonemGorev
    for og in OncekiDonemGorev.objects.filter(personel_id__in=kumulatif_sayac):
        kumulatif_sayac[og.personel_id]["komisyon"] += og.komisyon
        kumulatif_sayac[og.personel_id]["gozetmen"] += og.gozetmen

    sinav_toplam_komisyon = sum(v["komisyon"] for v in gorev_sayac.values())
    sinav_toplam_gozetmen = sum(v["gozetmen"] for v in gorev_sayac.values())
    sinav_toplam_gorev    = sinav_toplam_komisyon + sinav_toplam_gozetmen
    sinav_kbs_saat        = sinav_toplam_gorev * 5

    import json
    personel_kum_json = json.dumps({
        str(p.pk): {
            "k": kumulatif_sayac[p.pk]["komisyon"],
            "g": kumulatif_sayac[p.pk]["gozetmen"],
            "t": kumulatif_sayac[p.pk]["komisyon"] + kumulatif_sayac[p.pk]["gozetmen"],
        }
        for p in personel_listesi
    })

    return {
        "sinav": sinav,
        "oturumlar": oturumlar,
        "personel_listesi": personel_listesi,
        "personel_kum_json": personel_kum_json,
        "sinav_toplam_komisyon": sinav_toplam_komisyon,
        "sinav_toplam_gozetmen": sinav_toplam_gozetmen,
        "sinav_toplam_gorev":    sinav_toplam_gorev,
        "sinav_kbs_saat":        sinav_kbs_saat,
    }


@ust_yonetici_required
@require_POST
def gorevlendirme_oner(request, sinav_pk):
    """Komisyon/gözetmen görevlerini geçmiş görev yüküne ve branş/gün kısıtlarına göre
    otomatik olarak ÖNERİR. Veritabanına yazmaz — kullanıcı öneriyi inceleyip
    "Görevlendirmeleri Kaydet" ile onaylar, dropdown'ları elle düzenler ya da
    sayfayı yenileyip vazgeçebilir."""
    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)

    takvim_rows = list(
        SorumluTakvim.objects.filter(sinav=sinav).order_by("tarih", "oturum_no", "ders_adi")
    )
    if not takvim_rows:
        messages.error(request, "Önce sınav takvimini oluşturun.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

    active_salons: dict = {}
    for op in (
        SorumluOturmaPlani.objects
        .filter(sinav=sinav)
        .values("tarih", "oturum_no", "salon")
        .distinct()
    ):
        key = (op["tarih"], op["oturum_no"])
        active_salons.setdefault(key, set()).add(op["salon"])

    sonuc = oner_gorevlendirme(sinav, takvim_rows, active_salons)

    messages.info(
        request,
        "Öneri oluşturuldu ve HENÜZ KAYDEDİLMEDİ. Aşağıdaki dağılımı inceleyin; "
        "uygunsa \"Görevlendirmeleri Kaydet\" ile onaylayın, gerekirse dropdown'ları "
        "elle düzenleyin ya da sayfayı yenileyerek vazgeçin.",
    )
    for uyari in sonuc["uyarilar"]:
        messages.warning(request, uyari)

    context = _gorevlendirme_baglam(sinav, takvim_rows, active_salons, sonuc["komisyon"], sonuc["gozetmen"])
    context["oneri_modu"] = True
    return render(request, "sorumluluk/gorevlendirme.html", context)


@ust_yonetici_required
def gorevlendirme_pdf(request, sinav_pk):
    import io
    from sorumluluk.services.pdf_service import gorevlendirme_pdf_uret

    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)
    okul  = OkulBilgi.get()
    buf   = io.BytesIO()
    gorevlendirme_pdf_uret(buf, sinav, okul)
    buf.seek(0)

    donem  = sinav.get_donem_turu_display()  # type: ignore[attr-defined]
    egitim = str(sinav.egitim_yili) if sinav.egitim_yili else ""
    fname  = f"Gorevlendirme_{egitim}_{donem}.pdf".replace(" ", "_")
    return HttpResponse(
        buf.read(), content_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@ust_yonetici_required
def ogretmen_gorev_raporu_pdf(request, sinav_pk):
    import io
    from sorumluluk.services.pdf_service import ogretmen_gorev_raporu_pdf_uret

    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)
    okul  = OkulBilgi.get()
    buf   = io.BytesIO()
    ogretmen_gorev_raporu_pdf_uret(buf, sinav, okul)
    buf.seek(0)

    donem  = sinav.get_donem_turu_display()  # type: ignore[attr-defined]
    egitim = str(sinav.egitim_yili) if sinav.egitim_yili else ""
    fname  = f"OgretmenGorevRaporu_{egitim}_{donem}.pdf".replace(" ", "_")
    return HttpResponse(
        buf.read(), content_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@ust_yonetici_required
def ogrenci_takvim_pdf(request, sinav_pk):
    import io
    from sorumluluk.services.pdf_service import ogrenci_takvim_pdf_uret

    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)
    if not sinav.onaylandi:
        messages.error(request, "Rapor alabilmek için önce takvimi onaylamalısınız.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

    okul = OkulBilgi.get()
    buf  = io.BytesIO()
    ogrenci_takvim_pdf_uret(buf, sinav, okul)
    buf.seek(0)

    fname = f"Ogrenci_Sinav_Takvimi_{sinav.egitim_yili}_{sinav.get_donem_turu_display()}.pdf"
    return HttpResponse(buf.read(), content_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{fname}"'})


# ─────────────────────────────────────────────────────────
# Öğretmen Görev Özeti (Web Raporu)
# ─────────────────────────────────────────────────────────

@ust_yonetici_required
def ogretmen_gorev_imza_pdf(request, sinav_pk):
    import io
    from sorumluluk.services.pdf_service import ogretmen_gorev_imza_pdf_uret

    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)
    okul  = OkulBilgi.get()
    buf   = io.BytesIO()
    ogretmen_gorev_imza_pdf_uret(buf, sinav, okul)
    buf.seek(0)

    donem  = sinav.get_donem_turu_display()  # type: ignore[attr-defined]
    egitim = str(sinav.egitim_yili) if sinav.egitim_yili else ""
    fname  = f"OgretmenGorevImza_{egitim}_{donem}.pdf".replace(" ", "_")
    return HttpResponse(
        buf.read(), content_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@ust_yonetici_required
def ogretmen_gorev_ozeti(request):
    from itertools import groupby as iGroupBy
    from okul.models import Personel
    from sorumluluk.models import SALON_CHOICES as _SALON_CHOICES, OncekiDonemGorev, OncekiDonem

    _SALON_LABEL = dict(_SALON_CHOICES)
    _AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
              "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

    def _tr_tarih(d):
        return f"{d.day} {_AYLAR[d.month - 1]} {d.year}"

    sinav_pk = request.GET.get("sinav")
    sinavlar = list(SorumluSinav.objects.select_related("egitim_yili").order_by("-olusturma_tarihi"))
    secili_sinav = None

    if sinav_pk:
        try:
            secili_sinav = next(s for s in sinavlar if str(s.pk) == sinav_pk)
        except StopIteration:
            pass

    personel_listesi = list(Personel.objects.select_related("brans").order_by("brans__ad", "adi_soyadi"))
    pid_set = {p.pk for p in personel_listesi}

    def _komisyon_say(kayitlar_list):
        """Union-find: aynı slot veya aynı ders adı → 1 görev."""
        n = len(kayitlar_list)
        parent = list(range(n))
        for i in range(n):
            for j in range(i + 1, n):
                s_i, d_i, t_i, o_i = kayitlar_list[i]
                s_j, d_j, t_j, o_j = kayitlar_list[j]
                if s_i == s_j and ((t_i == t_j and o_i == o_j) or d_i == d_j):
                    ri, rj = i, j
                    while parent[ri] != ri:
                        ri = parent[ri]
                    while parent[rj] != rj:
                        rj = parent[rj]
                    if ri != rj:
                        parent[ri] = rj
        roots = set()
        for i in range(n):
            r = i
            while parent[r] != r:
                r = parent[r]
            roots.add(r)
        return len(roots)

    # ── Geçmiş dönem toplamları (tüm OncekiDonem kayıtlarının toplamı) ────────
    onceki_kum: dict = {}   # pid → {"komisyon": n, "gozetmen": n}
    for g in OncekiDonemGorev.objects.filter(personel_id__in=pid_set):
        entry = onceki_kum.setdefault(g.personel_id, {"komisyon": 0, "gozetmen": 0})
        entry["komisyon"] += g.komisyon
        entry["gozetmen"] += g.gozetmen

    gecmis_donemler = list(OncekiDonem.objects.all())

    # ── Kümülatif (tüm sınavlar — sistem kayıtları) ───────────────────────────
    sistem_kum = {p.pk: {"komisyon": 0, "gozetmen": 0} for p in personel_listesi}

    kum_komisyon_kayitlar: dict = {}
    for ku in SorumluKomisyonUyesi.objects.all():
        for pid in (ku.uye1_id, ku.uye2_id):
            if pid and pid in pid_set:
                kum_komisyon_kayitlar.setdefault(pid, []).append(
                    (ku.sinav_id, ku.ders_adi, ku.tarih, ku.oturum_no)
                )
    for pid, kayitlar in kum_komisyon_kayitlar.items():
        sistem_kum[pid]["komisyon"] = _komisyon_say(kayitlar)

    for gz in SorumluGozetmen.objects.all():
        if gz.gozetmen_id and gz.gozetmen_id in pid_set:
            sistem_kum[gz.gozetmen_id]["gozetmen"] += 1

    # ── Seçili sınav sayacı ve detayları ──────────────────────────────────────
    sinav_sayac = {p.pk: {"komisyon": 0, "gozetmen": 0} for p in personel_listesi}
    sinav_detaylar: dict = {}

    if secili_sinav:
        takvim_saatler = {
            (t.tarih, t.oturum_no): (t.saat_baslangic, t.saat_bitis)
            for t in SorumluTakvim.objects.filter(sinav=secili_sinav).order_by("tarih", "oturum_no")
        }

        sinav_komisyon_kayitlar: dict = {}
        for ku in SorumluKomisyonUyesi.objects.filter(sinav=secili_sinav):
            saatler = takvim_saatler.get((ku.tarih, ku.oturum_no))
            for pid in (ku.uye1_id, ku.uye2_id):
                if pid and pid in pid_set:
                    sinav_komisyon_kayitlar.setdefault(pid, []).append(
                        (ku.sinav_id, ku.ders_adi, ku.tarih, ku.oturum_no)
                    )
                    sinav_detaylar.setdefault(pid, []).append({
                        "tarih":          ku.tarih,
                        "tarih_str":      _tr_tarih(ku.tarih),
                        "oturum_no":      ku.oturum_no,
                        "saat_baslangic": saatler[0] if saatler else None,
                        "saat_bitis":     saatler[1] if saatler else None,
                        "tur":            "komisyon",
                        "detay":          ku.ders_adi,
                    })

        for pid, kayitlar in sinav_komisyon_kayitlar.items():
            sinav_sayac[pid]["komisyon"] = _komisyon_say(kayitlar)

        for gz in SorumluGozetmen.objects.filter(sinav=secili_sinav).select_related("gozetmen"):
            if gz.gozetmen_id and gz.gozetmen_id in pid_set:
                sinav_sayac[gz.gozetmen_id]["gozetmen"] += 1
                saatler = takvim_saatler.get((gz.tarih, gz.oturum_no))
                sinav_detaylar.setdefault(gz.gozetmen_id, []).append({
                    "tarih":          gz.tarih,
                    "tarih_str":      _tr_tarih(gz.tarih),
                    "oturum_no":      gz.oturum_no,
                    "saat_baslangic": saatler[0] if saatler else None,
                    "saat_bitis":     saatler[1] if saatler else None,
                    "tur":            "gozetmen",
                    "detay":          _SALON_LABEL.get(gz.salon, gz.salon),
                })

    # ── Tablo satırlarını oluştur ve branşa göre grupla ───────────────────────
    def _row(p):
        sys_k = sistem_kum[p.pk]["komisyon"]
        sys_g = sistem_kum[p.pk]["gozetmen"]
        onc   = onceki_kum.get(p.pk, {"komisyon": 0, "gozetmen": 0})
        onc_k = onc["komisyon"]
        onc_g = onc["gozetmen"]
        kum_k = sys_k + onc_k
        kum_g = sys_g + onc_g
        s_k   = sinav_sayac[p.pk]["komisyon"]
        s_g   = sinav_sayac[p.pk]["gozetmen"]
        return {
            "pk":           p.pk,
            "adi_soyadi":   p.adi_soyadi,
            "brans":        p.brans.ad if p.brans else "—",
            "komisyon":     s_k,
            "gozetmen":     s_g,
            "toplam":       s_k + s_g,
            "sys_komisyon": sys_k,
            "sys_gozetmen": sys_g,
            "onc_komisyon": onc_k,
            "onc_gozetmen": onc_g,
            "kum_komisyon": kum_k,
            "kum_gozetmen": kum_g,
            "kum_toplam":   kum_k + kum_g,
            "detaylar":     sorted(
                sinav_detaylar.get(p.pk, []),
                key=lambda x: (x["tarih"], x["oturum_no"], x["tur"]),
            ),
        }

    tum_satirlar = sorted(
        [_row(p) for p in personel_listesi],
        key=lambda x: (x["brans"], x["adi_soyadi"]),
    )

    gruplu_satirlar = [
        {"brans": brans, "satirlar": list(s_list)}
        for brans, s_list in iGroupBy(tum_satirlar, key=lambda x: x["brans"])
    ]

    toplam_komisyon = sum(s["komisyon"] if secili_sinav else s["kum_komisyon"] for g in gruplu_satirlar for s in g["satirlar"])
    toplam_gozetmen = sum(s["gozetmen"] if secili_sinav else s["kum_gozetmen"] for g in gruplu_satirlar for s in g["satirlar"])

    return render(request, "sorumluluk/ogretmen_gorev_ozeti.html", {
        "sinavlar":         sinavlar,
        "secili_sinav":     secili_sinav,
        "gruplu_satirlar":  gruplu_satirlar,
        "toplam_komisyon":  toplam_komisyon,
        "toplam_gozetmen":  toplam_gozetmen,
        "toplam_personel":  len(personel_listesi),
        "gecmis_donemler":  gecmis_donemler,
    })




# ─────────────────────────────────────────────────────────
# Öğretmen — Sorumluluk Sınavı Görevlerim
# ─────────────────────────────────────────────────────────

@login_required
def ogretmen_sorumluluk_gorevleri(request):
    from django.core.exceptions import PermissionDenied
    from django.db.models import Q
    from main.utils import _ogretmen_menu_gorumu
    from sorumluluk.models import (
        SorumluKomisyonUyesi,
        SorumluGozetmen,
        SorumluTakvim,
        SALON_CHOICES,
    )

    if not (request.user.is_superuser or _ogretmen_menu_gorumu(request.user)):
        raise PermissionDenied

    personel = getattr(request.user, "personel", None)
    if not personel:
        return render(request, "sorumluluk/ogretmen_sorumluluk_gorevleri.html", {
            "title": "Sınav Görevlerim",
            "hata": "Kullanıcınıza bağlı öğretmen kaydı bulunamadı.",
        })

    _SALON_LABEL = dict(SALON_CHOICES)
    _AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
              "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

    def _tr_tarih(d):
        return f"{d.day} {_AYLAR[d.month - 1]} {d.year}"

    komisyonlar = list(
        SorumluKomisyonUyesi.objects
        .filter(Q(uye1=personel) | Q(uye2=personel))
        .select_related("sinav", "sinav__egitim_yili")
        .order_by("sinav__id", "tarih", "oturum_no", "ders_adi")
    )
    gozetmenler = list(
        SorumluGozetmen.objects
        .filter(gozetmen=personel)
        .select_related("sinav", "sinav__egitim_yili")
        .order_by("sinav__id", "tarih", "oturum_no")
    )

    sinav_idler = {k.sinav_id for k in komisyonlar} | {g.sinav_id for g in gozetmenler}

    takvim_saatler = {}
    if sinav_idler:
        for t in SorumluTakvim.objects.filter(sinav_id__in=sinav_idler).order_by("sinav", "tarih", "oturum_no"):
            key = (t.sinav_id, t.tarih, t.oturum_no)
            if key not in takvim_saatler:
                takvim_saatler[key] = (t.saat_baslangic, t.saat_bitis)

    sinav_map: dict = {}

    def _oturum_al(sid, sinav_obj, tarih, oturum_no):
        if sid not in sinav_map:
            sinav_map[sid] = {"sinav": sinav_obj, "oturumlar": {}}
        oturum_key = (tarih, oturum_no)
        if oturum_key not in sinav_map[sid]["oturumlar"]:
            saatler = takvim_saatler.get((sid, tarih, oturum_no))
            sinav_map[sid]["oturumlar"][oturum_key] = {
                "tarih":         tarih,
                "tarih_str":     _tr_tarih(tarih),
                "oturum_no":     oturum_no,
                "saat_baslangic": saatler[0] if saatler else None,
                "saat_bitis":    saatler[1] if saatler else None,
                "komisyonlar":   [],
                "gozetmenler":   [],
            }
        return sinav_map[sid]["oturumlar"][oturum_key]

    for k in komisyonlar:
        ot = _oturum_al(k.sinav_id, k.sinav, k.tarih, k.oturum_no)
        ot["komisyonlar"].append(k.ders_adi)

    for g in gozetmenler:
        ot = _oturum_al(g.sinav_id, g.sinav, g.tarih, g.oturum_no)
        ot["gozetmenler"].append(_SALON_LABEL.get(g.salon, g.salon))

    gorev_sinavlar = [
        {
            "sinav": data["sinav"],
            "oturumlar": sorted(data["oturumlar"].values(), key=lambda x: (x["tarih"], x["oturum_no"])),
        }
        for _, data in sorted(sinav_map.items())
    ]

    return render(request, "sorumluluk/ogretmen_sorumluluk_gorevleri.html", {
        "title":          "Sınav Görevlerim",
        "gorev_sinavlar": gorev_sinavlar,
        "ogretmen_adi":   personel.adi_soyadi,
        "hata":           None if (komisyonlar or gozetmenler)
                          else "Henüz size atanmış sorumluluk sınavı görevi bulunmamaktadır.",
    })
