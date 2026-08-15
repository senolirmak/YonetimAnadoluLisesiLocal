from django import forms
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce

from secmelidersler.models import OrtakDers, SecmeliDers, SecmeliDersGrubu, get_toplam_saat

from .models import OgrenciSecmeliDers


class OgrenciSecmeliDersForm(forms.Form):

    def __init__(self, sinif_seviyesi, ogrenci=None, egitim_yili=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sinif_seviyesi = sinif_seviyesi
        self.ogrenci = ogrenci
        self.egitim_yili = egitim_yili

        ortak_qs = OrtakDers.objects.filter(sinif_seviyesi=sinif_seviyesi)
        if egitim_yili:
            ortak_qs = ortak_qs.filter(egitim_yili=egitim_yili)
        ortak_saat = ortak_qs.aggregate(toplam=Coalesce(Sum("haftalik_saat"), Value(0)))["toplam"]
        self.MAKS_SAAT = get_toplam_saat(sinif_seviyesi, egitim_yili=egitim_yili) - ortak_saat

        mevcut = {}
        if ogrenci:
            mevcut_qs = OgrenciSecmeliDers.objects.filter(
                ogrenci=ogrenci, ders__grup__sinif_seviyesi=sinif_seviyesi
            )
            if egitim_yili:
                mevcut_qs = mevcut_qs.filter(ders__grup__egitim_yili=egitim_yili)
            for secim in mevcut_qs.select_related("ders"):
                mevcut[secim.ders_id] = secim.secilen_saat

        grup_qs = SecmeliDersGrubu.objects.filter(sinif_seviyesi=sinif_seviyesi)
        if egitim_yili:
            grup_qs = grup_qs.filter(egitim_yili=egitim_yili)
        gruplar = grup_qs.prefetch_related("dersler").order_by("sira")

        self.grup_field_map = {}

        for grup in gruplar:
            field_items = []
            for ders in grup.dersler.filter(aktif=True).order_by("sira"):
                fname = f"ders_{ders.pk}"
                saat_lst = ders.saat_listesi

                self.fields[fname] = forms.BooleanField(required=False, label=ders.ders_adi)
                if ders.pk in mevcut:
                    self.initial[fname] = True

                if len(saat_lst) == 1:
                    field_items.append((fname, None, ders))
                else:
                    fname_saat = f"ders_{ders.pk}_saat"
                    choices = [(str(s), f"{s} saat") for s in saat_lst]
                    self.fields[fname_saat] = forms.ChoiceField(
                        required=False,
                        choices=choices,
                        label=f"{ders.ders_adi} — Saat",
                        widget=forms.RadioSelect,
                    )
                    self.initial[fname_saat] = str(mevcut.get(ders.pk, saat_lst[0]))
                    field_items.append((fname, fname_saat, ders))

            self.grup_field_map[grup.pk] = (grup, field_items)

    def get_secimler(self):
        result = []
        for grup, field_items in self.grup_field_map.values():
            for fname, fname_saat, ders in field_items:
                if not self.cleaned_data.get(fname):
                    continue
                if fname_saat is None:
                    result.append((ders, ders.sabit_saat))
                else:
                    try:
                        saat = int(self.cleaned_data.get(fname_saat) or 0)
                        if saat in ders.saat_listesi:
                            result.append((ders, saat))
                    except (ValueError, TypeError):
                        pass
        return result

    def clean(self):
        cleaned = super().clean()

        for grup, field_items in self.grup_field_map.values():
            for fname, fname_saat, ders in field_items:
                if fname_saat is None:
                    continue
                if cleaned.get(fname):
                    try:
                        saat = int(cleaned.get(fname_saat) or 0)
                        if saat not in ders.saat_listesi:
                            self.add_error(fname_saat, "Lütfen geçerli bir saat seçiniz.")
                    except (ValueError, TypeError):
                        self.add_error(fname_saat, "Lütfen ders saatini seçiniz.")

        secimler = self.get_secimler()
        toplam = sum(s for _, s in secimler)
        if toplam > self.MAKS_SAAT:
            raise forms.ValidationError(
                f"Seçilen derslerin toplam saati {toplam}'dir. En fazla {self.MAKS_SAAT} saat seçilebilir."
            )

        zorunlu_qs = SecmeliDersGrubu.objects.filter(
            sinif_seviyesi=self.sinif_seviyesi, zorunlu_grup=True
        )
        if self.egitim_yili:
            zorunlu_qs = zorunlu_qs.filter(egitim_yili=self.egitim_yili)
        zorunlu_qs = zorunlu_qs.prefetch_related("dersler")

        secilen_ids = {ders.pk for ders, _ in secimler}
        secilen_zorunlu = sum(
            1 for g in zorunlu_qs
            if set(g.dersler.filter(aktif=True).values_list("pk", flat=True)) & secilen_ids
        )
        zorunlu_toplam = zorunlu_qs.count()

        if zorunlu_toplam > 0 and toplam > 0:
            if self.sinif_seviyesi in (9, 10) and secilen_zorunlu < zorunlu_toplam:
                raise forms.ValidationError(
                    "9. ve 10. sınıf öğrencileri zorunlu ders gruplarının (İnsan-Toplum-Bilim, "
                    "Din-Ahlak-Değer, Kültür-Sanat-Spor) her birinden en az bir ders seçmelidir."
                )
            elif self.sinif_seviyesi in (11, 12) and secilen_zorunlu < 2 and zorunlu_toplam >= 2:
                raise forms.ValidationError(
                    "11. ve 12. sınıf öğrencileri zorunlu ders gruplarının en az ikisinden "
                    "birer ders seçmelidir."
                )

        # Bir dersin öğrenci başına en fazla kaç kez seçilebileceği (bkz.
        # SecmeliDersHavuzu.secimsayisi) — bu ENGELLEYİCİ bir hata değil, yalnızca
        # bilgilendirici bir uyarıdır; kaydetmeyi durdurmaz. `kaydet()` sonrası
        # çağıran view bu listeyi `messages.warning()`a çevirir.
        if self.ogrenci:
            from secmelidersler.services.secim_sayisi import secim_sayisi_asim_uyarilari
            self.secim_sayisi_uyarilari = secim_sayisi_asim_uyarilari(
                self.ogrenci, secimler, haric_egitim_yili=self.egitim_yili
            )
        else:
            self.secim_sayisi_uyarilari = []

        return cleaned

    def kaydet(self):
        if not self.ogrenci:
            return
        eski_qs = OgrenciSecmeliDers.objects.filter(
            ogrenci=self.ogrenci,
            ders__grup__sinif_seviyesi=self.sinif_seviyesi,
        )
        if self.egitim_yili:
            eski_qs = eski_qs.filter(ders__grup__egitim_yili=self.egitim_yili)
        eski_qs.delete()
        for ders, saat in self.get_secimler():
            OgrenciSecmeliDers.objects.create(
                ogrenci=self.ogrenci,
                ders=ders,
                secilen_saat=saat,
            )
