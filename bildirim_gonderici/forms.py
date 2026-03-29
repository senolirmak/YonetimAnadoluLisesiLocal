from django import forms

from .models import SinifTahta


class SinifTahtaForm(forms.ModelForm):
    class Meta:
        model = SinifTahta
        fields = ["sinif_sube", "ip_adresi", "port", "aktif", "aciklama"]
        labels = {
            "sinif_sube": "Sınıf / Şube",
            "ip_adresi":  "IP Adresi",
            "port":       "Port",
            "aktif":      "Aktif",
            "aciklama":   "Açıklama",
        }
        widgets = {
            "ip_adresi": forms.TextInput(attrs={"placeholder": "192.168.1.101"}),
            "port":      forms.NumberInput(attrs={"min": 1, "max": 65535}),
            "aciklama":  forms.TextInput(attrs={"placeholder": "İsteğe bağlı not"}),
        }
