from sinav.models import OturmaPlani, OturmaUretim, SinavSalonYoklama, Takvim


def slot_temizle(uretim, tarih, saat, oturum, takvim_de_sil: bool) -> dict:
    """Belirtilen (tarih, saat, oturum) slotu için OturmaPlani + OturmaUretim
    kayıtlarını siler; `takvim_de_sil=True` ise ayrıca Takvim kaydını da siler.

    Bu (tarih, saat) için başka oturum kalmadıysa SinavSalonYoklama kayıtları
    da temizlenir — `takvim_de_sil` durumuna göre "başka oturum kaldı mı"
    kontrolü Takvim ya da OturmaPlani üzerinden yapılır (ikisi ayrı yaşam
    döngüsüne sahip: slot_serbest_birak sadece oturma planını siler, Takvim
    kaydı kalır; takvim_slot_sil ise slotu takvimden tamamen kaldırır).

    Returns: {"op_sayisi": silinen oturma planı sayısı, "takvim_sayisi": silinen takvim kaydı sayısı}
    """
    op_sayisi = OturmaPlani.objects.filter(
        uretim=uretim, tarih=tarih, saat=saat, oturum=oturum
    ).count()
    OturmaPlani.objects.filter(
        uretim=uretim, tarih=tarih, saat=saat, oturum=oturum
    ).delete()
    OturmaUretim.objects.filter(
        takvim_uretim=uretim, tarih=tarih, saat=saat, oturum=oturum
    ).delete()

    takvim_sayisi = 0
    if takvim_de_sil:
        takvim_sayisi, _ = Takvim.objects.filter(
            uretim=uretim, tarih=tarih, saat=saat, oturum=oturum
        ).delete()
        # Takvim.CASCADE ile SinavMedia otomatik silindi.
        baska_oturum_var = Takvim.objects.filter(
            uretim=uretim, tarih=tarih, saat=saat
        ).exists()
    else:
        baska_oturum_var = OturmaPlani.objects.filter(
            uretim=uretim, tarih=tarih, saat=saat
        ).exists()

    if not baska_oturum_var:
        SinavSalonYoklama.objects.filter(
            uretim=uretim, tarih=tarih, saat=saat
        ).delete()

    return {"op_sayisi": op_sayisi, "takvim_sayisi": takvim_sayisi}
