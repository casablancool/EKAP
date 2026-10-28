"""İhale kaynağı arayüzü. EKAP dışında bir kaynak eklenecekse bu protokolü uygular."""
from datetime import date
from typing import Protocol

from src.modeller import IhaleHam


class KaynakHatasi(Exception):
    """Kaynak bütünüyle okunamadığında (erişim yok, beklenmeyen biçim)."""


class Kaynak(Protocol):
    ad: str

    def yeni_ihaleleri_getir(self, since: date) -> list[IhaleHam]: ...
