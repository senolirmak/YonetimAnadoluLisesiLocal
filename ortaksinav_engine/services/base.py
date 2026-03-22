class BaseService:
    """Tum servisler icin ortak temel sinif."""

    def __init__(self, config: dict, log_fn=None, cancel_fn=None):
        self.config = config
        self._log_fn = log_fn or print
        self._cancel_fn = cancel_fn or (lambda: False)

    def log(self, msg: str):
        self._log_fn(msg)

    def is_cancelled(self) -> bool:
        return self._cancel_fn()
