# pano/signals.py
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import WORKING_DAYS, DersSaati


@receiver(post_save, sender=DersSaati)
def copy_monday_to_workdays(sender, instance: DersSaati, **kwargs):
    # Sadece Pazartesi kaydı girilince çalışsın
    if instance.gun != DersSaati.Gun.PAZARTESI:
        return

    # Pazartesi hariç diğer çalışma günlerine aynı saatleri yaz
    # (Pazartesi zaten instance olarak kaydedildi, tekrar kaydedilirse sinyal döngüye girer)
    with transaction.atomic():
        for gun in WORKING_DAYS:
            if gun == DersSaati.Gun.PAZARTESI:
                continue
            DersSaati.objects.update_or_create(
                gun=gun,
                ders_no=instance.ders_no,
                defaults={
                    "baslangic": instance.baslangic,
                    "sure_dk": instance.sure_dk,
                    "aktif": instance.aktif,
                },
            )
