from django import forms

from .models import DersDefteri


class DersDefterForm(forms.ModelForm):
    class Meta:
        model = DersDefteri
        fields = ["icerik"]
        widgets = {
            "icerik": forms.Textarea(attrs={"rows": 6, "placeholder": "İşlenen konu, ders planı..."}),
        }
        labels = {
            "icerik": "İşlenen Konu / Ders Planı",
        }
