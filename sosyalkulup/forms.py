from django import forms

from .models import SosyalKulup


class SosyalKulupForm(forms.ModelForm):
    class Meta:
        model = SosyalKulup
        fields = ["ad", "aciklama", "aktif"]
        widgets = {
            "aciklama": forms.Textarea(attrs={"rows": 3}),
        }
