from django import forms

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
                .order_by("soyadi", "adi")
            )
