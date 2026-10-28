"""İhale kaynağı arayüzü. EKAP dışında bir kaynak eklenecekse bu protokolü uygular."""
from datetime import date
from typing import Protocol

from src.modeller import IhaleHam


class KaynakHatasi(Exception):
    """Kaynak okunamadığında (erişim yok, bot koruması, beklenmeyen biçim).

    `kismi`: hata anına kadar toplanan ihaleler; çalışma bunlarla devam eder.
    """

    def __init__(self, mesaj: str, kismi: list[IhaleHam] | None = None):
        super().__init__(mesaj)
        self.kismi: list[IhaleHam] = list(kismi or [])


class Kaynak(Protocol):
    ad: str

    def yeni_ihaleleri_getir(self, since: date) -> list[IhaleHam]: ...
