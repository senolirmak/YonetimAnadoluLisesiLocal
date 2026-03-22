from django import forms
from datetime import date
import re

from .models import OkulBilgileri, SinavBilgisi


class OkulBilgileriForm(forms.ModelForm):
    class Meta:
        model = OkulBilgileri
        fields = ["okul_adi", "okul_kodu", "okul_muduru"]
        labels = {
            "okul_adi":   "Okul Adı",
            "okul_kodu":  "Okul Kodu",
            "okul_muduru": "Okul Müdürü",
        }


class SinavBilgisiForm(forms.ModelForm):
    class Meta:
        model = SinavBilgisi
        fields = ["egitim_ogretim_yili", "donem", "sinav_adi",
                  "sinav_baslangic_tarihi", "eokul_veri_tarihi"]
        labels = {
            "egitim_ogretim_yili": "Eğitim-Öğretim Yılı",
            "donem": "Dönem",
            "sinav_adi": "Sınav Adı",
            "sinav_baslangic_tarihi": "Sınav Başlangıç Tarihi",
            "eokul_veri_tarihi": "e-Okul Veri Tarihi",
        }
        widgets = {
            "sinav_baslangic_tarihi": forms.DateInput(attrs={"type": "date"}),
            "eokul_veri_tarihi": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "egitim_ogretim_yili": "Örnek: 2025-2026",
            "eokul_veri_tarihi": "e-Okul'dan veri çekildiği tarih",
        }


class VeriYukleForm(forms.Form):
    eokul_ogrenci_dosya = forms.FileField(
        label="e-Okul Ogrenci Listesi",
        widget=forms.FileInput(attrs={"accept": ".xlsx,.xls"}),
        help_text="OOG01001R020_*.xls / .xlsx",
    )
    eokul_haftalik_program_dosya = forms.FileField(
        label="e-Okul Haftalik Ders Programi",
        widget=forms.FileInput(attrs={"accept": ".xlsx,.xls"}),
        help_text="OOK11002_R01_*.xls / .xlsx",
    )
    uygulama_tarihi = forms.DateField(
        label="Programin Gecerli Oldugu Tarih",
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=date(2026, 2, 23),
    )


class AlgoritmaForm(forms.Form):
    baslangic_tarih = forms.DateField(
        label="Sinav Baslangic Tarihi",
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=date(2025, 1, 6),
    )
    # oturum_sayisi_gun alani kaldirildi:
    # gun basina oturum sayisi her zaman oturum_saatleri listesinin uzunlugundan turetilir.
    oturum_saatleri = forms.CharField(
        label="Oturum Saatleri (virgülle)",
        initial="08:50,10:30,12:10,13:35,14:25",
        help_text="Ornek: 08:50,10:30,12:10  (her oturum HH:MM formatinda)",
    )
    tatil_gunleri = forms.CharField(
        label="Tatil Gunleri (her satira YYYY-MM-DD)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "2026-01-01"}),
    )
    time_limit_phase1 = forms.IntegerField(
        label="ILP Faz-1 Sure Limiti (sn)", initial=300, min_value=30,
    )
    time_limit_phase2 = forms.IntegerField(
        label="ILP Faz-2 Sure Limiti (sn)", initial=120, min_value=30,
    )
    max_extra_days = forms.IntegerField(
        label="Maksimum Ek Gun", initial=10, min_value=1,
    )

    def clean_oturum_saatleri(self):
        raw = self.cleaned_data.get("oturum_saatleri", "")
        saatler = [s.strip() for s in raw.split(",") if s.strip()]
        if not saatler:
            raise forms.ValidationError("En az bir oturum saati girilmeli.")
        pattern = re.compile(r"^\d{2}:\d{2}$")
        hatali = [s for s in saatler if not pattern.match(s)]
        if hatali:
            raise forms.ValidationError(
                f"Gecersiz saat formati (HH:MM olmali): {', '.join(hatali)}"
            )
        return ",".join(saatler)

    def clean_tatil_gunleri(self):
        raw = self.cleaned_data.get("tatil_gunleri", "")
        hatali = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                date.fromisoformat(line)
            except ValueError:
                hatali.append(line)
        if hatali:
            raise forms.ValidationError(
                f"Gecersiz tarih formati (YYYY-MM-DD olmali): {', '.join(hatali)}"
            )
        return raw
