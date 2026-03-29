from django.apps import AppConfig


class BildirimGondericiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bildirim_gonderici"
    verbose_name = "Bildirim Gönderici"

    def ready(self):
        import bildirim_gonderici.signals  # noqa: F401
