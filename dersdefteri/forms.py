from django import forms
from django.db.models import IntegerField
from django.db.models.functions import Cast

from ogrenci.models import Ogrenci

from .models import DersDefteri


class DersDefterForm(forms.ModelForm):
    devamsiz_ogrenciler = forms.ModelMultipleChoiceField(
        queryset=Ogrenci.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Devamsız Öğrenciler",
    )

    class Meta:
        model = DersDefteri
        fields = ["icerik", "devamsiz_ogrenciler"]
        widgets = {
            "icerik": forms.Textarea(attrs={"rows": 6, "placeholder": "İşlenen konu, ders planı..."}),
        }
        labels = {
            "icerik": "İşlenen Konu / Ders Planı",
        }

    def __init__(self, *args, sinif_sube=None, **kwargs):
        super().__init__(*args, **kwargs)
        if sinif_sube:
            self.fields["devamsiz_ogrenciler"].queryset = (
                Ogrenci.objects.filter(sinif=sinif_sube.sinif, sube=sinif_sube.sube)
                .annotate(okulno_int=Cast("okulno", IntegerField()))
                .order_by("okulno_int")
            )
