from django.apps import AppConfig


class PanoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pano"

    def ready(self):
        import pano.signals  # noqa: F401
