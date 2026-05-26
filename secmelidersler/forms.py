from django import forms
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from .models import Alan, AlanDers, OrtakDers, SecmeliDers, SecmeliDersGrubu, OgrenciSecim

_TOPLAM_SAAT = 39  # Rehberlik (1 saat) hariç: 40 - 1


class OgrenciSecimForm(forms.Form):

    def __init__(self, sinif_seviyesi, ogrenci=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sinif_seviyesi = sinif_seviyesi
        self.ogrenci = ogrenci

        ortak_saat = OrtakDers.objects.filter(
            sinif_seviyesi=sinif_seviyesi
        ).aggregate(toplam=Coalesce(Sum("haftalik_saat"), Value(0)))["toplam"]
        self.MAKS_SAAT = _TOPLAM_SAAT - ortak_saat

        mevcut = {}
        if ogrenci:
            for secim in OgrenciSecim.objects.filter(
                ogrenci=ogrenci, ders__grup__sinif_seviyesi=sinif_seviyesi
            ).select_related("ders"):
                mevcut[secim.ders_id] = secim.secilen_saat

        gruplar = (
            SecmeliDersGrubu.objects.filter(sinif_seviyesi=sinif_seviyesi)
            .prefetch_related("dersler")
            .order_by("sira")
        )

        # grup_id → (grup_obj, [(fname, fname_saat_or_None, ders_obj), ...])
        self.grup_field_map = {}

        for grup in gruplar:
            field_items = []
            for ders in grup.dersler.filter(aktif=True).order_by("sira"):
                fname = f"ders_{ders.pk}"
                saat_lst = ders.saat_listesi

                # Her ders için daima bir checkbox
                self.fields[fname] = forms.BooleanField(required=False, label=ders.ders_adi)
                if ders.pk in mevcut:
                    self.initial[fname] = True

                if len(saat_lst) == 1:
                    # Sabit saat — ek alan yok
                    field_items.append((fname, None, ders))
                else:
                    # Çoklu saat seçeneği — ayrı radio alanı
                    fname_saat = f"ders_{ders.pk}_saat"
                    choices = [(str(s), f"{s} saat") for s in saat_lst]
                    self.fields[fname_saat] = forms.ChoiceField(
                        required=False,
                        choices=choices,
                        label=f"{ders.ders_adi} — Saat",
                        widget=forms.RadioSelect,
                    )
                    # Mevcut seçim varsa onu, yoksa ilk seçeneği default yap
                    self.initial[fname_saat] = str(mevcut.get(ders.pk, saat_lst[0]))
                    field_items.append((fname, fname_saat, ders))

            self.grup_field_map[grup.pk] = (grup, field_items)

    # ------------------------------------------------------------------

    def get_secimler(self):
        """Seçilen (ders, saat) çiftlerini döndürür."""
        result = []
        for grup, field_items in self.grup_field_map.values():
            for fname, fname_saat, ders in field_items:
                if not self.cleaned_data.get(fname):
                    continue  # Checkbox işaretlenmemiş
                if fname_saat is None:
                    # Sabit saat
                    result.append((ders, ders.sabit_saat))
                else:
                    try:
                        saat = int(self.cleaned_data.get(fname_saat) or 0)
                        if saat in ders.saat_listesi:
                            result.append((ders, saat))
                        else:
                            # Geçersiz saat — kaydetme (validation yakalar)
                            pass
                    except (ValueError, TypeError):
                        pass
        return result

    def clean(self):
        cleaned = super().clean()

        # Checkbox işaretli ama saat seçimi geçersiz olanları yakala
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
        ).prefetch_related("dersler")

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

        return cleaned

    def kaydet(self):
        if not self.ogrenci:
            return
        OgrenciSecim.objects.filter(
            ogrenci=self.ogrenci,
            ders__grup__sinif_seviyesi=self.sinif_seviyesi,
        ).delete()
        for ders, saat in self.get_secimler():
            OgrenciSecim.objects.create(
                ogrenci=self.ogrenci,
                ders=ders,
                secilen_saat=saat,
            )


class AlanForm(forms.ModelForm):
    class Meta:
        model = Alan
        fields = ["sinif_seviyesi", "adi"]

    # grup_ders_map: [(grup_obj, [(fname, fname_saat_or_None, ders_obj), ...]), ...]
    grup_field_map = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["sinif_seviyesi"].widget = forms.Select(
            choices=[(11, "11. Sınıf"), (12, "12. Sınıf")]
        )
        self.fields["sinif_seviyesi"].label = "Sınıf Seviyesi"
        self.fields["adi"].label = "Alan Adı"
        self.fields["adi"].widget.attrs.update({"placeholder": "Örn: MF, TM, DİL"})

        # Mevcut kayıtlı dersler ve saatleri
        mevcut = {}
        if self.instance.pk:
            for ad in AlanDers.objects.filter(alan=self.instance).select_related("ders"):
                mevcut[ad.ders_id] = ad.secilen_saat

        gruplar = (
            SecmeliDersGrubu.objects.filter(sinif_seviyesi__in=[11, 12])
            .prefetch_related("dersler")
            .order_by("sinif_seviyesi", "sira")
        )

        # grup_id → (grup_obj, [(fname, fname_saat_or_None, ders_obj), ...])
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

            if field_items:
                self.grup_field_map[grup.pk] = (grup, field_items)

    @property
    def sinif_bloklar(self):
        """
        Template için:
        [(sinif_seviyesi, [(grup, [(fname, fname_saat_or_None, ders, chk_bf, saat_bf_or_None)])]), ...]
        """
        result = {}
        for grup, field_items in self.grup_field_map.values():
            sv = grup.sinif_seviyesi
            if sv not in result:
                result[sv] = []
            entries = []
            for fname, fname_saat, ders in field_items:
                chk_bf = self[fname]
                saat_bf = self[fname_saat] if fname_saat else None
                entries.append((fname, fname_saat, ders, chk_bf, saat_bf))
            result[sv].append((grup, entries))
        return list(result.items())

    def get_secimler(self):
        """Seçilen (ders, saat) çiftlerini döndürür."""
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
        return cleaned

    def save(self, commit=True):
        alan = super().save(commit=commit)
        if commit:
            AlanDers.objects.filter(alan=alan).delete()
            AlanDers.objects.bulk_create([
                AlanDers(alan=alan, ders=ders, secilen_saat=saat)
                for ders, saat in self.get_secimler()
            ])
        return alan
