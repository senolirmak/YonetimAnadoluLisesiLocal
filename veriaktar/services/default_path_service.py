from pathlib import Path


class DefaultPath:
    """
    Dosya yollarını $HOME/NobetciVeri yapısına göre çözen yardımcı sınıf.
    """

    def __init__(self):
        self.HOME_DATA_DIR = Path.home() / "NobetciVeri"
        self.VERI_DIR = self.HOME_DATA_DIR / "veri"
        self.HAZIRLIK_DIR = self.HOME_DATA_DIR / "hazirlik"

        for d in (self.HOME_DATA_DIR, self.VERI_DIR, self.HAZIRLIK_DIR):
            d.mkdir(parents=True, exist_ok=True)

    def resolve_veri_path(self, p):
        p = Path(p)
        if p.is_absolute():
            return p
        return self.VERI_DIR / p

    def resolve_hazirlik_path(self, p):
        p = Path(p)
        if p.is_absolute():
            return p
        return self.HAZIRLIK_DIR / p
