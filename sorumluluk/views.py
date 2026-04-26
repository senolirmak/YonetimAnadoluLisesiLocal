import os
import tempfile
from datetime import datetime
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from okul.models import OkulBilgi
from sorumluluk.forms import (
    SorumluDersForm,
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
    SorumluOgrenci,
    SorumluOturmaPlani,
    SorumluSinav,
    SorumluSinavParametre,
    SorumluTakvim,
)
from sorumluluk.services.import_service import sorumluluk_excel_aktar
from sorumluluk.services.takvim_motoru import DjangoSinavTakvimiMotoru
from sorumluluk.services.takvim_service import oturma_plani_olustur


# ─── Sınav CRUD ────────────────────────────────────────────────────────────────

@login_required
def sinav_liste(request):
    sinavlar = SorumluSinav.objects.select_related("egitim_yili").all()
    aktif_sinav = sinavlar.first()

    stats = {}
    if aktif_sinav:
        stats = {
            "ogrenci": SorumluOgrenci.objects.filter(sinav=aktif_sinav).count(),
            "ders":    SorumluDersHavuzu.objects.filter(sinav=aktif_sinav).count(),
            "oturum":  SorumluTakvim.objects.filter(sinav=aktif_sinav)
                           .values_list("tarih", "oturum_no").distinct().count(),
        }

    onaylanan_sinavlar = sinavlar.filter(onaylandi=True)

    return render(request, "sorumluluk/sinav_liste.html", {
        "sinavlar": sinavlar,
        "aktif_sinav": aktif_sinav,
        "stats": stats,
        "onaylanan_sinavlar": onaylanan_sinavlar,
    })


@login_required
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


@login_required
def sinav_duzenle(request, pk):
    sinav = get_object_or_404(SorumluSinav, pk=pk)
    form  = SorumluSinavForm(request.POST or None, instance=sinav)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Sınav güncellendi.")
        return redirect("sorumluluk:sinav_detay", pk=pk)
    return render(request, "sorumluluk/sinav_form.html", {"form": form, "baslik": "Sınavı Düzenle", "sinav": sinav})


@login_required
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


@login_required
@require_POST
def sinav_sil(request, pk):
    sinav = get_object_or_404(SorumluSinav, pk=pk)
    sinav.delete()
    messages.success(request, "Sınav silindi.")
    return redirect("sorumluluk:sinav_liste")


# ─── Excel Import (sınava özgü) ────────────────────────────────────────────────

@login_required
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

@login_required
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


@login_required
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


@login_required
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


@login_required
@require_POST
def ogr_sil(request, pk):
    ogr = get_object_or_404(SorumluOgrenci, pk=pk)
    sinav_pk = ogr.sinav_id
    ogr.delete()
    messages.success(request, "Öğrenci silindi.")
    return redirect("sorumluluk:ogr_liste", sinav_pk=sinav_pk)


@login_required
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


@login_required
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


@login_required
@require_POST
def ogr_ders_sil(request, pk):
    ders = get_object_or_404(SorumluDers, pk=pk)
    sinav_pk = ders.ogrenci.sinav_id
    ders.delete()
    messages.success(request, "Ders silindi.")
    return redirect("sorumluluk:ogr_liste", sinav_pk=sinav_pk)


# ─── Takvim ────────────────────────────────────────────────────────────────────

@login_required
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
                bas   = parts[0].strip()
                bit   = parts[1].strip() if len(parts) > 1 else bas
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


@login_required
def takvim_detay(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)

    takvim_rows = list(
        SorumluTakvim.objects
        .filter(sinav=sinav)
        .order_by("tarih", "oturum_no", "ders_adi")
    )

    # Oturma planını tek seferde çek, (tarih, oturum_no) anahtarıyla grupla
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
            "salon1":         [k for k in kayitlar if k.salon == "Sorumluluk1"],
            "salon2":         [k for k in kayitlar if k.salon == "Sorumluluk2"],
        })

    return render(request, "sorumluluk/takvim_detay.html", {
        "sinav": sinav,
        "oturumlar_veri": oturumlar_veri,
    })


@login_required
@require_POST
def takvim_onayla(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)
    sinav.onaylandi  = True
    sinav.onay_tarihi = timezone.now()
    sinav.save(update_fields=["onaylandi", "onay_tarihi"])
    messages.success(request, "Takvim onaylandı.")
    return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)


@login_required
@require_POST
def takvim_onay_iptal(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav, pk=sinav_pk)
    sinav.onaylandi   = False
    sinav.onay_tarihi = None
    sinav.save(update_fields=["onaylandi", "onay_tarihi"])
    messages.success(request, "Onay kaldırıldı.")
    return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)


@login_required
def rapor(request, sinav_pk):
    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)
    if not sinav.onaylandi:
        messages.error(request, "Rapor için önce onaylayın.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

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
            "salon1":         [k for k in kayitlar if k.salon == "Sorumluluk1"],
            "salon2":         [k for k in kayitlar if k.salon == "Sorumluluk2"],
        })

    okul = OkulBilgi.get()
    return render(request, "sorumluluk/rapor.html", {
        "sinav": sinav,
        "oturumlar_veri": oturumlar_veri,
        "okul": okul,
    })


@login_required
def rapor_pdf(request, sinav_pk):
    import io
    from sorumluluk.services.pdf_service import rapor_pdf_uret

    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)
    if not sinav.onaylandi:
        messages.error(request, "PDF için önce takvimi onaylamalısınız.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

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
            "salon1":         [k for k in kayitlar if k.salon == "Sorumluluk1"],
            "salon2":         [k for k in kayitlar if k.salon == "Sorumluluk2"],
        })

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


@login_required
def rapor_imza_pdf(request, sinav_pk):
    import io
    from sorumluluk.services.pdf_service import rapor_pdf_uret

    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)
    if not sinav.onaylandi:
        messages.error(request, "PDF için önce takvimi onaylamalısınız.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

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
            "salon1":         [k for k in kayitlar if k.salon == "Sorumluluk1"],
            "salon2":         [k for k in kayitlar if k.salon == "Sorumluluk2"],
        })

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

@login_required
def rapor_genel_takvim_pdf(request, sinav_pk):
    import io
    from sorumluluk.services.pdf_service import genel_takvim_pdf_uret

    sinav = get_object_or_404(SorumluSinav.objects.select_related("egitim_yili"), pk=sinav_pk)
    if not sinav.onaylandi:
        messages.error(request, "PDF için önce takvimi onaylamalısınız.")
        return redirect("sorumluluk:takvim_detay", sinav_pk=sinav_pk)

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
            "salon1":         [k for k in kayitlar if k.salon == "Sorumluluk1"],
            "salon2":         [k for k in kayitlar if k.salon == "Sorumluluk2"],
        })

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

@login_required
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
