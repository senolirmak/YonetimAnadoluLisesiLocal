"""Yedekleme işlemleri için formlar."""

from django import forms


class YedekYuklemeForm(forms.Form):
    dosya = forms.FileField(
        label="Yedek dosyası (.dump)",
        help_text="pg_dump ile 'custom format' (-Fc) alınmış bir .dump dosyası seçin.",
    )

    def clean_dosya(self):
        dosya = self.cleaned_data["dosya"]
        if not dosya.name.lower().endswith(".dump"):
            raise forms.ValidationError("Dosya adı '.dump' ile bitmelidir.")
        return dosya


class MedyaYedekYuklemeForm(forms.Form):
    dosya = forms.FileField(
        label="Medya yedeği (.tar.gz)",
        help_text="Bu sistemden alınmış bir medya yedeği (.tar.gz) seçin.",
    )

    def clean_dosya(self):
        dosya = self.cleaned_data["dosya"]
        if not dosya.name.lower().endswith(".tar.gz"):
            raise forms.ValidationError("Dosya adı '.tar.gz' ile bitmelidir.")
        return dosya


class GeriYuklemeOnayForm(forms.Form):
    dosya_adi = forms.CharField(widget=forms.HiddenInput)
    dogrulama = forms.CharField(
        label="Yedek dosyasının adını yazarak onaylayın",
        help_text=(
            "Bu işlem geri alınamaz. Devam etmek için yukarıda gösterilen yedek "
            "dosyasının adını aynen yazın — bu, yanlışlıkla farklı bir yedeği geri "
            "yüklemenizi önlemek içindir."
        ),
    )
    onay = forms.BooleanField(
        label="Geri yüklemenin mevcut tüm verilerin üzerine yazacağını anlıyorum.",
        required=True,
    )

    def clean(self):
        cleaned_data = super().clean()
        dogrulama = cleaned_data.get("dogrulama")
        dosya_adi = cleaned_data.get("dosya_adi")
        if dogrulama and dosya_adi and dogrulama != dosya_adi:
            self.add_error("dogrulama", "Yedek dosyası adı hatalı yazıldı.")
        return cleaned_data
