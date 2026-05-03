from django import forms

from ekders.models import EkDersDonemi, EkDersOnay, OgretmenEkDers, Tatil


class EkDersDonemiForm(forms.ModelForm):
    class Meta:
        model = EkDersDonemi
        fields = ["ad", "baslangic_tarihi", "bitis_tarihi", "hafta_sayisi"]
        widgets = {
            "baslangic_tarihi": forms.DateInput(attrs={"type": "date"}),
            "bitis_tarihi":     forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        bas = cleaned.get("baslangic_tarihi")
        bit = cleaned.get("bitis_tarihi")
        if bas and bit and bit < bas:
            raise forms.ValidationError("Bitiş tarihi başlangıçtan önce olamaz.")
        return cleaned


class TatilForm(forms.ModelForm):
    class Meta:
        model = Tatil
        fields = ["ad", "baslangic", "bitis"]
        widgets = {
            "baslangic": forms.DateInput(attrs={"type": "date"}),
            "bitis":     forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        bas = cleaned.get("baslangic")
        bit = cleaned.get("bitis")
        if bas and bit and bit < bas:
            raise forms.ValidationError("Bitiş tarihi başlangıçtan önce olamaz.")
        return cleaned


class OgretmenEkDersForm(forms.ModelForm):
    class Meta:
        model = OgretmenEkDers
        fields = [
            "gorev_tipi",
            "pazartesi", "sali", "carsamba", "persembe",
            "cuma", "cumartesi", "pazar",
            "nobet_sayisi", "diger_zorunlu_saat", "notlar",
        ]
        widgets = {
            "notlar": forms.Textarea(attrs={"rows": 2}),
        }


class EkDersOnayForm(forms.ModelForm):
    class Meta:
        model = EkDersOnay
        fields = ["notlar"]
        widgets = {
            "notlar": forms.Textarea(attrs={"rows": 3, "placeholder": "Onay notu (isteğe bağlı)"}),
        }
