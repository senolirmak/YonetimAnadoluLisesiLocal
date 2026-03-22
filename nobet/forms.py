from django import forms
from django.utils import timezone


class NobetDagitimForm(forms.Form):
    baslangic_tarihi = forms.DateField(
        label="Hafta Başlangıç Tarihi",
        widget=forms.DateInput(attrs={"type": "date", "class": "vDateField"}, format="%Y-%m-%d"),
    )


class NobetDersDoldurmaForm(forms.Form):
    tarih = forms.DateField(
        label="Tarih",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date", "class": "vDateField"}, format="%Y-%m-%d"),
    )
    max_shifts = forms.IntegerField(
        label="Maksimum Görev",
        initial=2,
        min_value=1,
        max_value=3,
        widget=forms.NumberInput(attrs={"type": "range", "min": "1", "max": "3", "step": "1"}),
    )
