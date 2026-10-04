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


class FetSonucYukleForm(forms.Form):
    uygulama_tarihi = forms.DateField(
        label="Yeni Programın Uygulama Tarihi",
        widget=forms.DateInput(attrs={"type": "date", "class": "vDateField"}, format="%Y-%m-%d"),
        help_text="FET sonucu bu tarihli yeni bir program sürümü olarak kaydedilir.",
    )
    dosya = forms.FileField(
        label="FET Sonuç Dosyası (..._data_and_timetable.fet)",
        widget=forms.ClearableFileInput(attrs={"accept": ".fet"}),
    )


__all__ = ["DersProgramiImportForm", "FetSonucYukleForm", "SinifSubeSecimForm"]
