from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from dersprogrami.models import NobetDersProgrami

from .models import Duyuru


class DuyuruForm(forms.ModelForm):
    class Meta:
        model = Duyuru
        fields = ["sinif", "tarih", "ders_saati", "mesaj"]
        widgets = {
            "tarih": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "ders_saati": forms.NumberInput(attrs={"min": 1, "max": 20, "class": "form-control"}),
            "mesaj": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "sinif": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # HTML tarafında tarayıcının tarih seçicisinde bugünden önceki günleri kapatır
        self.fields["tarih"].widget.attrs["min"] = timezone.localdate().strftime("%Y-%m-%d")

        # Ders saatlerini veritabanından dinamik olarak alıp ChoiceField'a çevirelim
        try:
            # Ders programından benzersiz ve sıralı ders saatlerini al
            ders_saatleri_qs = (
                NobetDersProgrami.objects.order_by("ders_saati")
                .values_list("ders_saati", flat=True)
                .distinct()
            )

            if ders_saatleri_qs:
                choices = [(saat, f"{saat}. Ders") for saat in ders_saatleri_qs]

                # ders_saati alanını ChoiceField olarak yeniden tanımla
                self.fields["ders_saati"] = forms.ChoiceField(
                    choices=[("", "Ders Saati Seçiniz")] + choices,
                    label="Ders Saati",
                    widget=forms.Select(attrs={"class": "form-select"}),
                )
        except Exception:
            # Eğer bir hata oluşursa (örn. veritabanı hazır değilse),
            # Meta'da tanımlı varsayılan NumberInput widget'ı kullanılmaya devam eder.
            pass

    def clean_tarih(self):
        tarih = self.cleaned_data.get("tarih")
        # Arka planda ekstra güvenlik: Sunucuya geçmiş tarih gelirse engelle
        if tarih and tarih < timezone.localdate():
            raise ValidationError("Geçmiş bir tarihe duyuru ekleyemezsiniz.")
        return tarih

    def clean_ders_saati(self):
        ders_saati = self.cleaned_data.get("ders_saati")
        if not ders_saati:
            raise ValidationError("Lütfen bir ders saati seçiniz.")
        try:
            return int(ders_saati)
        except (ValueError, TypeError):
            raise ValidationError("Geçersiz ders saati değeri.")
