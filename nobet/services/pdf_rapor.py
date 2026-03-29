import os
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def get_report_header_info(target_date):
    """Verilen tarih için Eğitim Yılı, Dönem ve Hafta bilgisini döndürür."""
    simdi = target_date
    hafta_baslangici = simdi - timedelta(days=simdi.weekday())
    hafta_no = hafta_baslangici.isocalendar()[1]
    simdi_ay = simdi.month

    donem_sayi = {
        1: [9, 10, 11, 12, 1],
        2: [2, 3, 4, 5, 6],
    }

    donem_numarasi = next((k for k, v in donem_sayi.items() if simdi_ay in v), None)
    donem = f"{donem_numarasi}. Dönem" if donem_numarasi else "Yaz Dönemi"

    egitim_yili = (
        f"{simdi.year}-{simdi.year + 1}" if simdi_ay > 8 else f"{simdi.year - 1}-{simdi.year}"
    )
    return f"{egitim_yili} Eğitim Öğretim Yılı {donem} {hafta_no}. Hafta"


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

        header_info = get_report_header_info(self.target_date)
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
