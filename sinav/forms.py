from django import forms
from datetime import date
import re

from .models import SinavBilgisi


class SinavBilgisiForm(forms.ModelForm):
    class Meta:
        model = SinavBilgisi
        fields = [
            "egitim_yili_fk", "donem_fk",
            "sinav_adi",
            "sinav_baslangic_tarihi", "eokul_veri_tarihi",
        ]
        labels = {
            "egitim_yili_fk": "Eğitim-Öğretim Yılı",
            "donem_fk": "Dönem",
            "sinav_adi": "Sınav Adı",
            "sinav_baslangic_tarihi": "Sınav Başlangıç Tarihi",
            "eokul_veri_tarihi": "e-Okul Veri Tarihi",
        }
        widgets = {
            "sinav_baslangic_tarihi": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "eokul_veri_tarihi": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
        help_texts = {
            "eokul_veri_tarihi": "e-Okul'dan veri çekildiği tarih",
            "donem_fk": "Okul Ayarları sayfasından dönem eklenebilir.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from nobet.models import OkulDonem
        self.fields["egitim_yili_fk"].required = True
        self.fields["donem_fk"].required = True
        self.fields["donem_fk"].queryset = (
            OkulDonem.objects.select_related("egitim_yili").all()
        )
        self.fields["donem_fk"].label_from_instance = (
            lambda obj: f"{obj.egitim_yili} – {obj.get_donem_display()}"
        )



class AlgoritmaForm(forms.Form):
    baslangic_tarih = forms.DateField(
        label="Sınav Başlangıç Tarihi",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        initial=date(2025, 1, 6),
    )
    oturum_saatleri = forms.CharField(
        label="Oturum Saatleri",
        initial="08:50,10:30,12:10,13:35,14:25",
        help_text="Virgülle ayrılmış, HH:MM formatında. Örnek: 08:50,10:30,12:10",
    )
    tatil_gunleri = forms.CharField(
        label="Tatil Günleri",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "2026-01-01\n2026-04-23"}),
        help_text="Her satıra bir tarih, YYYY-AA-GG formatında.",
    )
    time_limit_phase1 = forms.IntegerField(
        label="Faz-1 Süre Limiti (sn)",
        initial=300,
        min_value=30,
        help_text="ILP minimum slot sayısı aşaması için zaman sınırı.",
    )
    time_limit_phase2 = forms.IntegerField(
        label="Faz-2 Süre Limiti (sn)",
        initial=120,
        min_value=30,
        help_text="ILP optimizasyon aşaması için zaman sınırı.",
    )
    max_extra_days = forms.IntegerField(
        label="Maksimum Ek Gün",
        initial=10,
        min_value=1,
        help_text="Çözüm bulunamazsa takvim kaç gün uzatılabilir.",
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
