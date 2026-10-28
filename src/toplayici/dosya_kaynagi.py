"""Yerel klasördeki IhaleHam JSON dosyalarını okuyan kaynak (EKAP toplayıcısı gelene kadar)."""
import logging
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from src.modeller import IhaleHam
from src.toplayici.kaynak import KaynakHatasi

logger = logging.getLogger(__name__)


class DosyaKaynagi:
    ad = "dosya"

    def __init__(self, dizin: Path):
        self.dizin = Path(dizin)

    def yeni_ihaleleri_getir(self, since: date) -> list[IhaleHam]:
        if not self.dizin.is_dir():
            raise KaynakHatasi(f"ilan dizini yok: {self.dizin}")
        ihaleler = []
        for yol in sorted(self.dizin.glob("*.json")):
            try:
                ihale = IhaleHam.model_validate_json(yol.read_text(encoding="utf-8"))
            except (ValidationError, OSError, UnicodeDecodeError):
                logger.warning("bozuk ilan dosyası atlandı: %s", yol)
                continue
            if ihale.yayin_tarihi is None or ihale.yayin_tarihi >= since:
                ihaleler.append(ihale)
        return ihaleler
