from datetime import timedelta

from django import forms

from nobet.models import NobetOgretmen

from .models import Devamsizlik


class DevamsizlikForm(forms.ModelForm):
    ogretmen = forms.ModelChoiceField(
        queryset=NobetOgretmen.objects.select_related("personel").order_by("personel__adi_soyadi"),
        widget=forms.Select(attrs={"class": "vSelect"}),
        label="Öğretmen",
    )

    tum_gun = forms.BooleanField(
        label="Tüm Gün (Tüm Dersler)",
        required=False,
        initial=True,
        help_text="İşaretlenirse tüm ders saatleri (1-8) için devamsız sayılır.",
    )

    secilen_saatler = forms.MultipleChoiceField(
        choices=[(str(i), f"{i}. Ders") for i in range(1, 9)],
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label="Devamsız Olduğu Saatler",
    )

    goreve_baslama_tarihi = forms.CharField(
        label="Göreve Başlama Tarihi",
        required=False,
        widget=forms.TextInput(
            attrs={"class": "vTextField", "readonly": "readonly", "id": "id_goreve_baslama_tarihi"}
        ),
    )

    durum = forms.CharField(
        label="Durum",
        required=False,
        widget=forms.TextInput(
            attrs={"class": "vTextField", "readonly": "readonly", "id": "id_durum"}
        ),
    )

    field_order = [
        "ogretmen",
        "baslangic_tarihi",
        "devamsiz_tur",
        "sure",
        "goreve_baslama_tarihi",
        "durum",
        "aciklama",
        "tum_gun",
        "secilen_saatler",
        "gorevlendirme_yapilsin",
    ]

    class Media:
        js = ("js/devamsizlik_calculations.js",)

    class Meta:
        model = Devamsizlik
        fields = [
            "ogretmen",
            "baslangic_tarihi",
            "devamsiz_tur",
            "sure",
            "aciklama",
            "tum_gun",
            "secilen_saatler",
            "gorevlendirme_yapilsin",
        ]
        widgets = {
            "baslangic_tarihi": forms.DateInput(
                attrs={"type": "date", "class": "vDateField", "id": "id_baslangic_tarihi"},
                format="%Y-%m-%d",
            ),
            "devamsiz_tur": forms.Select(attrs={"class": "vSelect"}),
            "sure": forms.NumberInput(attrs={"class": "vIntegerField", "id": "id_sure"}),
            "aciklama": forms.TextInput(attrs={"class": "vTextField"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.baslangic_tarihi:
            tarih = self.instance.baslangic_tarihi + timedelta(days=self.instance.sure)
            self.fields["goreve_baslama_tarihi"].initial = tarih.strftime("%d.%m.%Y")
            self.fields["durum"].initial = self.instance.durum

        if self.instance and self.instance.pk and self.instance.ders_saatleri:
            saatler = self.instance.ders_saatleri.split(",")
            self.fields["secilen_saatler"].initial = saatler
            self.fields["tum_gun"].initial = len(saatler) >= 8

    def clean(self):
        cleaned_data = super().clean()
        tum_gun = cleaned_data.get("tum_gun")
        secilen = cleaned_data.get("secilen_saatler")

        if tum_gun:
            self.instance.ders_saatleri = "1,2,3,4,5,6,7,8"
        elif secilen:
            self.instance.ders_saatleri = ",".join(secilen)
        else:
            self.instance.ders_saatleri = "1,2,3,4,5,6,7,8"

        return cleaned_data
