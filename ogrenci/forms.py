from django import forms
from django.core.validators import RegexValidator

from .models import OgrenciAdres, OgrenciDetay

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
