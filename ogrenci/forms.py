from django import forms
from django.core.validators import RegexValidator

from .models import Ogrenci, OgrenciAdres, OgrenciDetay

telefon_validator = RegexValidator(
    regex=r"^\(5\d{2}\) \d{3} \d{2} \d{2}$",
    message="Geçerli bir numara girin. Örn: (5xx) xxx xx xx",
)

TELEFON_WIDGET = forms.TextInput(
    attrs={
        "class": "vTextField telefon-input",
        "type": "tel",
        "placeholder": "(5xx) xxx xx xx",
        "maxlength": "15",
    }
)


class OgrenciDetayForm(forms.ModelForm):
    velitelefon = forms.CharField(
        required=False,
        label="Veli Telefon",
        validators=[telefon_validator],
        widget=TELEFON_WIDGET,
    )
    annetelefon = forms.CharField(
        required=False,
        label="Anne Telefon",
        validators=[telefon_validator],
        widget=TELEFON_WIDGET,
    )
    babatelefon = forms.CharField(
        required=False,
        label="Baba Telefon",
        validators=[telefon_validator],
        widget=TELEFON_WIDGET,
    )

    class Meta:
        model = OgrenciDetay
        exclude = ["ogrenci"]
        widgets = {
            "babaadi": forms.TextInput(attrs={"class": "vTextField"}),
            "anneadi": forms.TextInput(attrs={"class": "vTextField"}),
            "veli": forms.TextInput(attrs={"class": "vTextField"}),
        }

    def clean_velitelefon(self):
        return self.cleaned_data.get("velitelefon") or None

    def clean_annetelefon(self):
        return self.cleaned_data.get("annetelefon") or None

    def clean_babatelefon(self):
        return self.cleaned_data.get("babatelefon") or None


class OgrenciForm(forms.ModelForm):
    class Meta:
        model = Ogrenci
        fields = ["okulno", "sube", "tckimlikno", "adi", "soyadi", "dogumtarihi", "cinsiyet"]
        widgets = {
            "okulno": forms.NumberInput(attrs={"class": "vTextField"}),
            "sube": forms.TextInput(attrs={"class": "vTextField", "maxlength": "2"}),
            "tckimlikno": forms.TextInput(attrs={"class": "vTextField", "maxlength": "11"}),
            "adi": forms.TextInput(attrs={"class": "vTextField"}),
            "soyadi": forms.TextInput(attrs={"class": "vTextField"}),
            "dogumtarihi": forms.DateInput(attrs={"class": "vTextField", "type": "date"}),
        }

    def clean_sube(self):
        sube = (self.cleaned_data.get("sube") or "").strip().upper()
        if self.instance.pk and self.instance.sinif and sube != self.instance.sube:
            from okul.models import SinifSube

            kayit = SinifSube.objects.filter(sinif=self.instance.sinif, sube__iexact=sube).first()
            if kayit and not kayit.acik:
                raise forms.ValidationError(
                    f"{self.instance.sinif}/{sube} şubesi kapalı — öğrenci bu şubeye taşınamaz."
                )
        return sube


class OgrenciAdresForm(forms.ModelForm):
    class Meta:
        model = OgrenciAdres
        exclude = ["ogrenci"]
        widgets = {
            "il": forms.TextInput(attrs={"class": "vTextField"}),
            "ilce": forms.TextInput(attrs={"class": "vTextField"}),
            "mahalle": forms.TextInput(attrs={"class": "vTextField"}),
            "postakodu": forms.TextInput(attrs={"class": "vTextField"}),
            "adres": forms.Textarea(attrs={"class": "vLargeTextField", "rows": 3}),
        }
