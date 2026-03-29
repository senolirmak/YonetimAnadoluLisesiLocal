from django import forms

from okul.models import SinifSube
from veriaktar.forms import DersProgramiImportForm


class SinifSubeSecimForm(forms.Form):
    sinif_sube = forms.ModelChoiceField(
        queryset=SinifSube.objects.order_by("sinif", "sube"),
        label="Sınıf / Şube",
        empty_label="-- Sınıf seçiniz --",
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "onchange": "this.form.submit()"}),
    )


__all__ = ["DersProgramiImportForm", "SinifSubeSecimForm"]
