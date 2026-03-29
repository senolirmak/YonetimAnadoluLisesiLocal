# -*- coding: utf-8 -*-
from django import forms
from okul.models import DersHavuzu


class DersHavuzuForm(forms.ModelForm):
    class Meta:
        model = DersHavuzu
        fields = ["cift_oturum", "sinav_yapilmayacak"]
        widgets = {
            "cift_oturum": forms.Select(attrs={"class": "form-select form-select-sm"}),
            "sinav_yapilmayacak": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
