import os
from datetime import datetime, time
from io import BytesIO

import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from dersprogrami.models import NobetDersProgrami
from personeldevamsizlik.models import Devamsizlik
from utility.services.main_services import IstatistikService
from utility.services.nobet_dagitimi_service import AdvancedNobetDagitim

from ..forms import NobetDersDoldurmaForm
from ..models import (
    NobetAtanamayan,
    NobetGecmisi,
    NobetOgretmen,
    NobetPersonel,
)
from .dagitim import _get_report_header_info, _gun_adi_tr
from .permissions import is_mudur_yardimcisi, is_yonetici

# ─────────────────────────────────────────────
# PDF Rapor Yardımcı Sınıfı
# ─────────────────────────────────────────────


class NobetPDFReport:
    """PDF Rapor oluşturma işlemlerini yöneten yardımcı sınıf."""

    def __init__(self, buffer, target_date, title, dynamic_height=False, row_count=0):
        self.buffer = buffer
        self.target_date = target_date
        self.title = title
        self.dynamic_height = dynamic_height
        self.row_count = row_count
        self.elements = []
        self.styles = getSampleStyleSheet()
        self.font_name = "Helvetica"
        self.font_name_bold = "Helvetica-Bold"
        self._register_fonts()
        self._init_document()

    def _register_fonts(self):
        try:
            font_path = os.path.join(settings.BASE_DIR, "main", "static", "fonts", "DejaVuSans.ttf")
            font_path_bold = os.path.join(
                settings.BASE_DIR, "main", "static", "fonts", "DejaVuSans-Bold.ttf"
            )
            pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", font_path_bold))
            self.font_name = "DejaVuSans"
            self.font_name_bold = "DejaVuSans-Bold"
        except Exception:
            pass

    def _init_document(self):
        page_width, page_height = A4
        if self.dynamic_height:
            estimated_height = 150 + (self.row_count * 30)
            page_height = max(estimated_height, 200)

        self.pagesize = (page_width, page_height)

        self.title_style = self.styles["h1"]
        self.title_style.fontName = self.font_name_bold
        self.title_style.alignment = 1

        self.header_style = ParagraphStyle(
            name="Header", fontName=self.font_name_bold, textColor=colors.whitesmoke, alignment=1
        )
        self.cell_style = ParagraphStyle(name="Cell", fontName=self.font_name, alignment=1)

        self.header_style_small = ParagraphStyle(
            name="HeaderSmall",
            fontName=self.font_name_bold,
            fontSize=10,
            parent=self.styles["Normal"],
            textColor=colors.whitesmoke,
        )
        self.cell_style_small = ParagraphStyle(
            name="CellSmall", fontName=self.font_name, fontSize=9, parent=self.styles["Normal"]
        )

    def add_header(self, custom_title_color=None):
        if custom_title_color:
            self.title_style.textColor = custom_title_color

        header_info = _get_report_header_info(self.target_date)
        self.elements.append(Paragraph(header_info, self.title_style))
        self.elements.append(Paragraph(self.title, self.title_style))
        self.elements.append(Spacer(1, 20))

    def add_table(self, data, col_widths, style=None):
        t = Table(data, colWidths=col_widths)
        if style:
            t.setStyle(style)
        self.elements.append(t)

    def build(self):
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=self.pagesize,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=30,
        )
        doc.build(self.elements)


# ─────────────────────────────────────────────
# Ders Doldurma View
# ─────────────────────────────────────────────


@login_required
def nobet_ders_doldurma(request):
    if not is_yonetici(request.user):
        raise PermissionDenied
    assignments = []
    unassigned = []
    personel_map = {}
    max_shifts = 2
    current_view_datetime = None

    SESS_KEY_ASSIGN = "nobet_assignments"
    SESS_KEY_UNASSIGN = "nobet_unassigned"
    SESS_KEY_DATE = "nobet_target_date"

    def get_history_records(t_date):
        wd_map = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 7, 6: 1}
        d_wd = wd_map.get(t_date.weekday(), 2)

        d1 = set(NobetGecmisi.objects.filter(tarih__week_day=d_wd).values_list("tarih", flat=True))
        d2 = set(
            NobetAtanamayan.objects.filter(tarih__week_day=d_wd).values_list("tarih", flat=True)
        )
        return sorted(list(d1 | d2), reverse=True)[:5]

    if request.method == "POST":
        if ("kaydet" in request.POST or "sil" in request.POST) and not is_mudur_yardimcisi(
            request.user
        ):
            raise PermissionDenied
        if "kaydet" in request.POST:
            assignments = request.session.get(SESS_KEY_ASSIGN, [])
            unassigned = request.session.get(SESS_KEY_UNASSIGN, [])
            date_str = request.session.get(SESS_KEY_DATE)
            target_date = timezone.localdate()

            if date_str:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                kayit_zamani = timezone.localtime().replace(
                    year=target_date.year, month=target_date.month, day=target_date.day
                )
                current_view_datetime = kayit_zamani

                for item in assignments:
                    try:
                        ogretmen = (
                            NobetOgretmen.objects.filter(
                                personel_id=item["teacher_id"], uygulama_tarihi__lte=target_date
                            )
                            .order_by("-uygulama_tarihi")
                            .first()
                        )

                        if ogretmen:
                            NobetGecmisi.objects.create(
                                saat=item["hour"],
                                sinif=item["class"],
                                devamsiz=item["absent_teacher_id"],
                                tarih=kayit_zamani,
                                atandi=1,
                                ogretmen=ogretmen,
                            )
                    except Exception as e:
                        print(f"Hata (Atama Kaydı): {e}")

                for item in unassigned:
                    try:
                        ogretmen = (
                            NobetOgretmen.objects.filter(
                                personel_id=item["absent_teacher_id"],
                                uygulama_tarihi__lte=target_date,
                            )
                            .order_by("-uygulama_tarihi")
                            .first()
                        )

                        if ogretmen:
                            NobetAtanamayan.objects.create(
                                saat=item["hour"],
                                sinif=item["class"],
                                tarih=kayit_zamani,
                                atandi=0,
                                ogretmen=ogretmen,
                            )
                    except Exception as e:
                        print(f"Hata (Atanamayan Kaydı): {e}")

                try:
                    istatistik_service = IstatistikService()
                    istatistik_service.hesapla_ve_kaydet()
                except Exception as e:
                    print(f"İstatistik güncelleme hatası: {e}")

                messages.success(
                    request,
                    f"{target_date.strftime('%d.%m.%Y')} tarihi için atamalar başarıyla kaydedildi.",
                )

            form = NobetDersDoldurmaForm(initial={"tarih": target_date, "max_shifts": 2})

            all_ids = set()
            for a in assignments:
                all_ids.add(a["teacher_id"])
                all_ids.add(a["absent_teacher_id"])
            for u in unassigned:
                all_ids.add(u["absent_teacher_id"])

            personel_map = {
                p.pk: p.adi_soyadi for p in NobetPersonel.objects.filter(id__in=all_ids)
            }
            history_records = get_history_records(target_date)

            context = {
                "title": "Nöbetçi Öğretmen Ders Doldurma",
                "form": form,
                "assignments": assignments,
                "unassigned": unassigned,
                "personel_map": personel_map,
                "target_date": target_date,
                "history_records": history_records,
                "loaded_from_db": True,
                "current_view_datetime": current_view_datetime,
            }
            return render(request, "nobet_ders_doldurma.html", context)

        elif "sil" in request.POST:
            delete_dt_str = request.POST.get("delete_datetime")
            if delete_dt_str:
                try:
                    del_dt = datetime.strptime(delete_dt_str, "%Y-%m-%d %H:%M:%S")
                    target_date = del_dt.date()

                    start_dt = timezone.make_aware(del_dt.replace(microsecond=0))
                    end_dt = timezone.make_aware(del_dt.replace(microsecond=999999))

                    NobetGecmisi.objects.filter(tarih__range=[start_dt, end_dt]).delete()
                    NobetAtanamayan.objects.filter(tarih__range=[start_dt, end_dt]).delete()

                    try:
                        istatistik_service = IstatistikService()
                        istatistik_service.hesapla_ve_kaydet()
                    except Exception as e:
                        print(f"İstatistik güncelleme hatası: {e}")

                    messages.success(
                        request, f"{del_dt.strftime('%d.%m.%Y %H:%M:%S')} tarihli kayıtlar silindi."
                    )
                    return redirect(f"{request.path}?tarih={target_date.strftime('%Y-%m-%d')}")
                except ValueError:
                    messages.error(request, "Silme işlemi için tarih formatı geçersiz.")
                    target_date = timezone.localdate()
            else:
                form = NobetDersDoldurmaForm(request.POST)
                if form.is_valid():
                    target_date = form.cleaned_data["tarih"]
                    start_dt = timezone.make_aware(datetime.combine(target_date, time.min))
                    end_dt = timezone.make_aware(datetime.combine(target_date, time.max))

                    NobetGecmisi.objects.filter(tarih__range=[start_dt, end_dt]).delete()
                    NobetAtanamayan.objects.filter(tarih__range=[start_dt, end_dt]).delete()

                    try:
                        istatistik_service = IstatistikService()
                        istatistik_service.hesapla_ve_kaydet()
                    except Exception as e:
                        print(f"İstatistik güncelleme hatası: {e}")

                    messages.success(
                        request, f"{target_date.strftime('%d.%m.%Y')} tarihli kayıtlar silindi."
                    )
                    return redirect(f"{request.path}?tarih={target_date.strftime('%Y-%m-%d')}")
                else:
                    target_date = timezone.localdate()

        else:
            form = NobetDersDoldurmaForm(request.POST)
            if form.is_valid():
                target_date = form.cleaned_data["tarih"]
                max_shifts = form.cleaned_data.get("max_shifts", 2)
            else:
                target_date = timezone.localdate()
    elif request.GET.get("tarih"):
        tarih_str = request.GET.get("tarih")
        try:
            dt_obj = datetime.strptime(tarih_str, "%Y-%m-%d %H:%M:%S")
            target_date = dt_obj.date()
        except (ValueError, TypeError):
            try:
                target_date = datetime.strptime(tarih_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                target_date = timezone.localdate()
        form = NobetDersDoldurmaForm(initial={"tarih": target_date, "max_shifts": 2})
    else:
        target_date = timezone.localdate()
        form = NobetDersDoldurmaForm(initial={"tarih": target_date, "max_shifts": 2})

    loaded_from_db = False
    mode = request.GET.get("mode")
    view_dt_override = None

    if request.method == "GET" and not mode:
        start_day = timezone.make_aware(datetime.combine(target_date, time.min))
        end_day = timezone.make_aware(datetime.combine(target_date, time.max))

        latest_rec = (
            NobetGecmisi.objects.filter(tarih__range=[start_day, end_day])
            .order_by("-tarih")
            .first()
        )
        latest_un = (
            NobetAtanamayan.objects.filter(tarih__range=[start_day, end_day])
            .order_by("-tarih")
            .first()
        )

        found_dt = None
        if latest_rec and latest_un:
            found_dt = latest_rec.tarih if latest_rec.tarih >= latest_un.tarih else latest_un.tarih
        elif latest_rec:
            found_dt = latest_rec.tarih
        elif latest_un:
            found_dt = latest_un.tarih

        if found_dt:
            mode = "view"
            view_dt_override = found_dt

    if request.method == "GET" and mode == "view":
        tarih_str = request.GET.get("tarih")
        view_dt = None

        if view_dt_override:
            view_dt = view_dt_override
        elif tarih_str:
            try:
                view_dt = datetime.strptime(tarih_str, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass

        if view_dt:
            if timezone.is_naive(view_dt):
                current_view_datetime = timezone.make_aware(view_dt)
                start_dt = timezone.make_aware(view_dt.replace(microsecond=0))
                end_dt = timezone.make_aware(view_dt.replace(microsecond=999999))
            else:
                current_view_datetime = view_dt
                start_dt = view_dt.replace(microsecond=0)
                end_dt = view_dt.replace(microsecond=999999)
        else:
            start_dt = timezone.make_aware(datetime.combine(target_date, time.min))
            end_dt = timezone.make_aware(datetime.combine(target_date, time.max))

        saved_assigns = NobetGecmisi.objects.filter(tarih__range=[start_dt, end_dt]).select_related(
            "ogretmen__personel"
        )
        saved_unassigns = NobetAtanamayan.objects.filter(
            tarih__range=[start_dt, end_dt]
        ).select_related("ogretmen__personel")

        if saved_assigns.exists() or saved_unassigns.exists():
            loaded_from_db = True

            query_date = view_dt.date() if view_dt else target_date
            absent_records = Devamsizlik.objects.filter(
                baslangic_tarihi__lte=query_date, bitis_tarihi__gte=query_date
            ).select_related("ogretmen__personel")
            absent_map = {
                r.ogretmen.personel.pk: r.get_devamsiz_tur_display() for r in absent_records
            }

            all_ids = set()

            for s in saved_assigns:
                t_id = s.ogretmen.personel.pk
                abs_id = s.devamsiz
                all_ids.add(t_id)
                all_ids.add(abs_id)

                assignments.append(
                    {
                        "hour": s.saat,
                        "class": s.sinif,
                        "teacher_id": t_id,
                        "absent_teacher_id": abs_id,
                        "devamsiz_tur": absent_map.get(abs_id, "-"),
                    }
                )

            for u in saved_unassigns:
                abs_id = u.ogretmen.personel.pk
                all_ids.add(abs_id)

                unassigned.append(
                    {
                        "hour": u.saat,
                        "class": u.sinif,
                        "absent_teacher_id": abs_id,
                        "devamsiz_tur": absent_map.get(abs_id, "-"),
                    }
                )

            r_date = view_dt.date() if view_dt else target_date
            request.session["nobet_assignments"] = assignments
            request.session["nobet_unassigned"] = unassigned
            request.session["nobet_target_date"] = r_date.strftime("%Y-%m-%d")

            messages.info(
                request,
                f"{view_dt.strftime('%d.%m.%Y %H:%M:%S')} tarihli kayıtlı dağılım gösteriliyor.",
            )

    if not loaded_from_db and request.method == "POST" and "hesapla" in request.POST:
        days_map = {
            0: "Monday",
            1: "Tuesday",
            2: "Wednesday",
            3: "Thursday",
            4: "Friday",
            5: "Saturday",
            6: "Sunday",
        }
        day_name_en = days_map[target_date.weekday()]

        program_date = (
            NobetDersProgrami.objects.filter(uygulama_tarihi__lte=target_date)
            .order_by("-uygulama_tarihi")
            .values_list("uygulama_tarihi", flat=True)
            .first()
        )

        if not program_date:
            program_date = (
                NobetDersProgrami.objects.order_by("-uygulama_tarihi")
                .values_list("uygulama_tarihi", flat=True)
                .first()
            )

        from ..models import NobetGorevi

        gorev_date = (
            NobetGorevi.objects.filter(uygulama_tarihi__lte=target_date)
            .order_by("-uygulama_tarihi")
            .values_list("uygulama_tarihi", flat=True)
            .first()
        )

        absent_records = Devamsizlik.objects.filter(
            baslangic_tarihi__lte=target_date,
            bitis_tarihi__gte=target_date,
            gorevlendirme_yapilsin=True,
        ).select_related("ogretmen__personel")

        absent_teacher_ids = [r.ogretmen.personel.pk for r in absent_records]

        absent_teachers_data = []
        for r in absent_records:
            p_id = r.ogretmen.personel.pk

            allowed_hours = (
                [int(h) for h in r.ders_saatleri.split(",") if h.strip().isdigit()]
                if hasattr(r, "ders_saatleri") and r.ders_saatleri
                else list(range(1, 9))
            )

            lessons = NobetDersProgrami.objects.filter(
                ogretmen__id=p_id,
                gun=day_name_en,
                uygulama_tarihi=program_date,
                ders_saati__in=allowed_hours,
            ).select_related("sinif_sube")

            dersleri = {ders.ders_saati: str(ders.sinif_sube) for ders in lessons if ders.sinif_sube}
            if dersleri:
                absent_teachers_data.append(
                    {
                        "ogretmen_id": p_id,
                        "adi_soyadi": r.ogretmen.personel.adi_soyadi,
                        "devamsiz_tur": r.get_devamsiz_tur_display(),
                        "dersleri": dersleri,
                    }
                )

        if gorev_date:
            duty_records = NobetGorevi.objects.filter(
                uygulama_tarihi=gorev_date, nobet_gun=day_name_en
            ).select_related("ogretmen__personel")
        else:
            duty_records = []

        duty_teacher_ids = [r.ogretmen.personel.pk for r in duty_records]

        available_teachers_data = []
        stats_dict = {}

        for r in duty_records:
            p_id = r.ogretmen.personel.pk

            if p_id in absent_teacher_ids:
                continue

            lessons = NobetDersProgrami.objects.filter(
                ogretmen__id=p_id, gun=day_name_en, uygulama_tarihi=program_date
            ).select_related("sinif_sube")
            dersleri = {ders.ders_saati: str(ders.sinif_sube) for ders in lessons if ders.sinif_sube}

            available_teachers_data.append(
                {
                    "ogretmen_id": p_id,
                    "adi_soyadi": r.ogretmen.personel.adi_soyadi,
                    "dersleri": dersleri,
                }
            )

            try:
                s = r.ogretmen.istatistikler
                stats_dict[p_id] = {
                    "haftalik_ortalama": s.haftalik_ortalama,
                    "agirlikli_puan": s.agirlikli_puan,
                    "toplam_nobet": s.toplam_nobet,
                    "hafta_sayisi": s.hafta_sayisi,
                    "son_nobet_tarihi": s.son_nobet_tarihi,
                    "son_nobet_yeri": s.son_nobet_yeri,
                }
            except Exception:
                pass

        solver = AdvancedNobetDagitim(max_shifts=max_shifts)
        solver.set_teacher_statistics(stats_dict)
        result = solver.optimize(available_teachers_data, absent_teachers_data)

        assignments = result.get("assignments", [])
        unassigned = result.get("unassigned", [])

        absent_info = {t["ogretmen_id"]: t["devamsiz_tur"] for t in absent_teachers_data}

        for assignment in assignments:
            assignment["devamsiz_tur"] = absent_info.get(assignment["absent_teacher_id"], "")

        for unassigned_item in unassigned:
            unassigned_item["devamsiz_tur"] = absent_info.get(
                unassigned_item["absent_teacher_id"], ""
            )

        request.session[SESS_KEY_ASSIGN] = assignments
        request.session[SESS_KEY_UNASSIGN] = unassigned
        request.session[SESS_KEY_DATE] = target_date.strftime("%Y-%m-%d")

        personel_map = {
            p.id: p.adi_soyadi
            for p in NobetPersonel.objects.filter(id__in=duty_teacher_ids + absent_teacher_ids)
        }

    if loaded_from_db:
        all_ids = set()
        for a in assignments:
            all_ids.add(a["teacher_id"])
            all_ids.add(a["absent_teacher_id"])
        for u in unassigned:
            all_ids.add(u["absent_teacher_id"])
        personel_map = {p.id: p.adi_soyadi for p in NobetPersonel.objects.filter(id__in=all_ids)}

    history_records = get_history_records(target_date)

    context = {
        "title": "Nöbetçi Öğretmen Ders Doldurma",
        "form": form,
        "assignments": assignments,
        "unassigned": unassigned,
        "personel_map": personel_map,
        "target_date": target_date,
        "history_records": history_records,
        "loaded_from_db": loaded_from_db,
        "current_view_datetime": current_view_datetime,
    }
    return render(request, "nobet_ders_doldurma.html", context)


# ─────────────────────────────────────────────
# Ders Doldurma İndirme Fonksiyonları
# ─────────────────────────────────────────────


def _generate_pdf_bytes(request, dynamic_height=False):
    """
    Hafızada bir PDF raporu oluşturur ve byte dizisi olarak döndürür.
    Veri yoksa (None, None) döndürür.
    """
    tarih_str = request.GET.get("tarih")
    assignments = []
    target_date = None

    if tarih_str:
        start_dt = None
        end_dt = None
        try:
            view_dt = datetime.strptime(tarih_str, "%Y-%m-%d %H:%M:%S")
            target_date = view_dt.date()
            start_dt = timezone.make_aware(view_dt.replace(microsecond=0))
            end_dt = timezone.make_aware(view_dt.replace(microsecond=999999))
        except ValueError:
            try:
                target_date = datetime.strptime(tarih_str, "%Y-%m-%d").date()
                start_day = timezone.make_aware(datetime.combine(target_date, time.min))
                end_day = timezone.make_aware(datetime.combine(target_date, time.max))
                latest_rec = (
                    NobetGecmisi.objects.filter(tarih__range=[start_day, end_day])
                    .order_by("-tarih")
                    .first()
                )
                latest_un = (
                    NobetAtanamayan.objects.filter(tarih__range=[start_day, end_day])
                    .order_by("-tarih")
                    .first()
                )

                found_dt = None
                if latest_rec and latest_un:
                    found_dt = (
                        latest_rec.tarih if latest_rec.tarih >= latest_un.tarih else latest_un.tarih
                    )
                elif latest_rec:
                    found_dt = latest_rec.tarih
                elif latest_un:
                    found_dt = latest_un.tarih

                if found_dt:
                    start_dt = found_dt.replace(microsecond=0)
                    end_dt = found_dt.replace(microsecond=999999)
            except ValueError:
                pass

        if start_dt and end_dt:
            saved_assigns = NobetGecmisi.objects.filter(
                tarih__range=[start_dt, end_dt]
            ).select_related("ogretmen__personel")
            if saved_assigns.exists():
                query_date = target_date
                absent_records = Devamsizlik.objects.filter(
                    baslangic_tarihi__lte=query_date, bitis_tarihi__gte=query_date
                ).select_related("ogretmen__personel")
                absent_map = {
                    r.ogretmen.personel.pk: r.get_devamsiz_tur_display() for r in absent_records
                }

                for s in saved_assigns:
                    assignments.append(
                        {
                            "hour": s.saat,
                            "class": s.sinif,
                            "teacher_id": s.ogretmen.personel.pk,
                            "absent_teacher_id": s.devamsiz,
                            "devamsiz_tur": absent_map.get(s.devamsiz, "-"),
                        }
                    )

    if not assignments:
        assignments = request.session.get("nobet_assignments", [])
        date_str = request.session.get(
            "nobet_target_date", timezone.localdate().strftime("%Y-%m-%d")
        )
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    if not assignments:
        messages.error(request, "Rapor oluşturmak için atanmış ders bulunamadı.")
        return None, None

    all_ids = set()
    for item in assignments:
        all_ids.add(item.get("teacher_id"))
        all_ids.add(item.get("absent_teacher_id"))
    personeller = NobetPersonel.objects.filter(id__in=all_ids)
    personel_map = {p.pk: p.adi_soyadi for p in personeller}
    brans_map = {p.pk: p.brans for p in personeller}

    pdf_buffer = BytesIO()

    report = NobetPDFReport(
        pdf_buffer,
        target_date,
        f"Nöbetçi Öğretmen Ders Doldurma Listesi ({target_date.strftime('%d.%m.%Y')} {_gun_adi_tr(target_date)})",
        dynamic_height,
        len(assignments),
    )
    report.add_header()

    styled_header = [
        Paragraph(cell, report.header_style_small)
        for cell in [
            "Ders Saati",
            "Sınıf",
            "Devamsız Öğretmen",
            "Mazeret",
            "Görevlendirilen Nöbetçi",
            "Branş",
        ]
    ]
    table_data = [styled_header]

    for item in sorted(assignments, key=lambda x: x.get("hour", 0)):
        table_data.append(
            [
                Paragraph(f"{item.get('hour', '?')}. Ders", report.cell_style_small),
                Paragraph(str(item.get("class", "")), report.cell_style_small),
                Paragraph(
                    personel_map.get(item.get("absent_teacher_id"), "-"), report.cell_style_small
                ),
                Paragraph(str(item.get("devamsiz_tur", "")), report.cell_style_small),
                Paragraph(
                    f"<b>{personel_map.get(item.get('teacher_id'), '-')}</b>",
                    report.cell_style_small,
                ),
                Paragraph(brans_map.get(item.get("teacher_id"), "-"), report.cell_style_small),
            ]
        )

    page_width = report.pagesize[0] - 60

    style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F81BD")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]
        + [
            ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#DCE6F1"))
            for i in range(1, len(table_data))
            if i % 2 != 0
        ]
    )

    report.add_table(
        table_data,
        col_widths=[
            page_width * 0.1,
            page_width * 0.1,
            page_width * 0.25,
            page_width * 0.15,
            page_width * 0.25,
            page_width * 0.15,
        ],
        style=style,
    )
    report.build()

    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()

    return pdf_bytes, target_date


@login_required
def download_ders_doldurma_pdf(request):
    pdf_bytes, target_date = _generate_pdf_bytes(request)
    if not pdf_bytes:
        return redirect("nobet_ders_doldurma")

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="ders_doldurma_{target_date.strftime("%Y-%m-%d")}.pdf"'
    )
    response.write(pdf_bytes)
    return response


@login_required
def download_ders_doldurma_png(request):
    from pdf2image import convert_from_bytes

    pdf_bytes, target_date = _generate_pdf_bytes(request, dynamic_height=True)
    if not pdf_bytes:
        return redirect("nobet_ders_doldurma")

    try:
        images = convert_from_bytes(pdf_bytes, dpi=150)
        if images:
            response = HttpResponse(content_type="image/png")
            response["Content-Disposition"] = (
                f'attachment; filename="ders_doldurma_{target_date.strftime("%Y-%m-%d")}.png"'
            )
            img_buffer = BytesIO()
            images[0].save(img_buffer, format="PNG")
            response.write(img_buffer.getvalue())
            img_buffer.close()
            return response
    except Exception as e:
        messages.error(
            request,
            f"Rapor resme dönüştürülürken bir hata oluştu. Lütfen sistem yöneticinize 'poppler' kütüphanesinin kurulu olduğunu teyit ettirin. Hata: {e}",
        )
        return redirect("nobet_ders_doldurma")

    messages.error(request, "Rapor resmi oluşturulamadı.")
    return redirect("nobet_ders_doldurma")


@login_required
def download_ders_doldurma_xlsx(request):
    tarih_str = request.GET.get("tarih")
    assignments = []
    target_date = None

    if tarih_str:
        start_dt = None
        end_dt = None
        try:
            view_dt = datetime.strptime(tarih_str, "%Y-%m-%d %H:%M:%S")
            target_date = view_dt.date()
            start_dt = timezone.make_aware(view_dt.replace(microsecond=0))
            end_dt = timezone.make_aware(view_dt.replace(microsecond=999999))
        except ValueError:
            try:
                target_date = datetime.strptime(tarih_str, "%Y-%m-%d").date()
                start_day = timezone.make_aware(datetime.combine(target_date, time.min))
                end_day = timezone.make_aware(datetime.combine(target_date, time.max))
                latest_rec = (
                    NobetGecmisi.objects.filter(tarih__range=[start_day, end_day])
                    .order_by("-tarih")
                    .first()
                )
                latest_un = (
                    NobetAtanamayan.objects.filter(tarih__range=[start_day, end_day])
                    .order_by("-tarih")
                    .first()
                )

                found_dt = None
                if latest_rec and latest_un:
                    found_dt = (
                        latest_rec.tarih if latest_rec.tarih >= latest_un.tarih else latest_un.tarih
                    )
                elif latest_rec:
                    found_dt = latest_rec.tarih
                elif latest_un:
                    found_dt = latest_un.tarih

                if found_dt:
                    start_dt = found_dt.replace(microsecond=0)
                    end_dt = found_dt.replace(microsecond=999999)
            except ValueError:
                pass

        if start_dt and end_dt:
            saved_assigns = NobetGecmisi.objects.filter(
                tarih__range=[start_dt, end_dt]
            ).select_related("ogretmen__personel")
            if saved_assigns.exists():
                query_date = target_date
                absent_records = Devamsizlik.objects.filter(
                    baslangic_tarihi__lte=query_date, bitis_tarihi__gte=query_date
                ).select_related("ogretmen__personel")
                absent_map = {
                    r.ogretmen.personel.pk: r.get_devamsiz_tur_display() for r in absent_records
                }

                for s in saved_assigns:
                    assignments.append(
                        {
                            "hour": s.saat,
                            "class": s.sinif,
                            "teacher_id": s.ogretmen.personel.pk,
                            "absent_teacher_id": s.devamsiz,
                            "devamsiz_tur": absent_map.get(s.devamsiz, "-"),
                        }
                    )

    if not assignments:
        assignments = request.session.get("nobet_assignments", [])
        date_str = request.session.get(
            "nobet_target_date", timezone.localdate().strftime("%Y-%m-%d")
        )
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    if not assignments:
        messages.error(request, "Rapor oluşturmak için atanmış ders bulunamadı.")
        return redirect("nobet_ders_doldurma")

    all_ids = set()
    for item in assignments:
        all_ids.add(item.get("teacher_id"))
        all_ids.add(item.get("absent_teacher_id"))
    personeller = NobetPersonel.objects.filter(id__in=all_ids)
    personel_map = {p.pk: p.adi_soyadi for p in personeller}
    brans_map = {p.pk: p.brans for p in personeller}

    report_data = []
    for item in sorted(assignments, key=lambda x: x.get("hour", 0)):
        report_data.append(
            {
                "Ders Saati": f"{item.get('hour', '?')}. Ders",
                "Sınıf": str(item.get("class", "")),
                "Devamsız Öğretmen": personel_map.get(item.get("absent_teacher_id"), "-"),
                "Mazeret": str(item.get("devamsiz_tur", "")),
                "Görevlendirilen Nöbetçi": personel_map.get(item.get("teacher_id"), "-"),
                "Nöbetçi Branşı": brans_map.get(item.get("teacher_id"), "-"),
            }
        )

    df = pd.DataFrame(report_data)

    header_info = _get_report_header_info(target_date)
    title_text = f"{header_info} - Ders Doldurma Listesi ({target_date.strftime('%d.%m.%Y')} {_gun_adi_tr(target_date)})"

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Ders Doldurma", startrow=2)
        worksheet = writer.sheets["Ders Doldurma"]
        worksheet["A1"] = title_text

        for i, col in enumerate(df.columns):
            column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.column_dimensions[chr(65 + i)].width = column_len

    output.seek(0)

    response = HttpResponse(
        output, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="ders_doldurma_{target_date.strftime("%Y-%m-%d")}.xlsx"'
    )

    return response
