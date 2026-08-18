"""Yedekleme işlemleri için formlar."""

from django import forms
from django.conf import settings


class GeriYuklemeOnayForm(forms.Form):
    dosya_adi = forms.CharField(widget=forms.HiddenInput)
    dogrulama = forms.CharField(
        label="Veritabanı adını yazarak onaylayın",
        help_text="Bu işlem geri alınamaz. Devam etmek için veritabanının adını aynen yazın.",
    )
    onay = forms.BooleanField(
        label="Geri yüklemenin mevcut tüm verilerin üzerine yazacağını anlıyorum.",
        required=True,
    )

    def clean_dogrulama(self):
        deger = self.cleaned_data["dogrulama"]
        beklenen = settings.DATABASES["default"]["NAME"]
        if deger != beklenen:
            raise forms.ValidationError("Veritabanı adı hatalı yazıldı.")
        return deger
