from okul.models import SinifSube


def sinif_sube_kaydet(sinif_bilgileri):
    SinifSube.objects.all().delete()
    objs = []
    for sinif, subeler in sinif_bilgileri.items():
        for sube in subeler:
            objs.append(SinifSube(sinif=sinif, sube=sube))
    SinifSube.objects.bulk_create(objs, ignore_conflicts=True)
