# Register your models here.
from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import redirect
from django.urls import path

from .models import DersSaati, Duyuru, Etkinlik, KioskAyar, MedyaIcerik


@admin.register(Duyuru)
class DuyuruAdmin(admin.ModelAdmin):
    list_display = ("id", "aktif", "sira", "baslik", "metin", "baslangic", "bitis", "guncelleme")
    list_filter = ("aktif",)
    search_fields = ("baslik", "metin", "etiket")
    ordering = ("sira", "-olusturma")


@admin.register(DersSaati)
class DersSaatiAdmin(admin.ModelAdmin):
    list_display = ("id", "aktif", "gun", "ders_no", "baslangic", "sure_dk")
    list_filter = ("aktif", "gun")
    ordering = ("gun", "ders_no")
    list_editable = ("aktif", "baslangic", "sure_dk")

    # ✅ Admin listesine özel template (buton için)
    change_list_template = "admin/pano/derssaati/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "copy-monday/",
                self.admin_site.admin_view(self.copy_monday),
                name="pano_derssaati_copy_monday",
            ),
        ]
        return custom + urls

    def copy_monday(self, request):
        # İstersen Cumartesi de olsun: target_days = [2,3,4,5,6]
        target_days = [2, 3, 4, 5, 6, 7]  # Salı..Cuma

        monday_qs = DersSaati.objects.filter(gun=DersSaati.Gun.PAZARTESI, aktif=True).order_by(
            "ders_no"
        )
        if not monday_qs.exists():
            messages.error(
                request,
                "Pazartesi için aktif ders saati bulunamadı. Önce Pazartesi ders saatlerini girin.",
            )
            return redirect("..")

        created = 0
        updated = 0

        with transaction.atomic():
            for src in monday_qs:
                for day in target_days:
                    obj, was_created = DersSaati.objects.update_or_create(
                        gun=day,
                        ders_no=src.ders_no,
                        defaults={
                            "baslangic": src.baslangic,
                            "sure_dk": src.sure_dk,
                            "aktif": src.aktif,
                        },
                    )
                    if was_created:
                        created += 1
                    else:
                        updated += 1

        messages.success(
            request,
            f"Pazartesi ders saatleri kopyalandı. Oluşturulan: {created}, Güncellenen: {updated} (Salı–Cuma).",
        )
        return redirect("..")


@admin.register(Etkinlik)
class EtkinlikAdmin(admin.ModelAdmin):
    list_display = ("id", "aktif", "baslik", "baslangic", "bitis", "yer")
    list_filter = ("aktif",)
    search_fields = ("baslik", "aciklama", "yer")
    ordering = ("-baslangic",)
    list_editable = ("aktif",)


@admin.register(MedyaIcerik)
class MedyaIcerikAdmin(admin.ModelAdmin):
    list_display = ("id", "aktif", "sira", "baslik", "aciklama", "tur", "sure", "dosya")
    list_filter = ("aktif", "tur")
    list_editable = ("aktif", "sira", "sure")
    ordering = ("sira", "-olusturma")


@admin.register(KioskAyar)
class KioskAyarAdmin(admin.ModelAdmin):
    list_display = ("id", "aktif", "ana_sayfa_sure", "etkinlik_sure", "efekt", "updated_at")
    list_editable = ("aktif", "ana_sayfa_sure", "etkinlik_sure", "efekt")
    list_display_links = ("id",)  # ✅ ilk link alanı id oldu
