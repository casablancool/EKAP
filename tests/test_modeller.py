from pathlib import Path

import pytest
from pydantic import ValidationError

from src.modeller import FirmaProfili


def _profil(**degisiklik) -> dict:
    temel = {"ad": "Örnek Ltd.", "eposta": ["bilgi@ornek.com.tr"], "ihale_turleri": ["mal"]}
    temel.update(degisiklik)
    return temel


def test_ornek_profil_gecerli():
    FirmaProfili.model_validate_json(Path("profil.json").read_text(encoding="utf-8"))


def test_yapim_normalize():
    assert FirmaProfili(**_profil(ihale_turleri=["Yapım"])).ihale_turleri == ["yapim"]


def test_aralik_ters():
    with pytest.raises(ValidationError, match="tipik_ihale_buyuklugu"):
        FirmaProfili(**_profil(tipik_ihale_buyuklugu={"min_tl": 5_000_000, "max_tl": 1_000_000}))


def test_bilinmeyen_alan():
    with pytest.raises(ValidationError):
        FirmaProfili(**_profil(telefon="0312"))


def test_eposta_gecersiz():
    with pytest.raises(ValidationError):
        FirmaProfili(**_profil(eposta=["firma.com"]))


def test_profil_ozeti():
    a, b = FirmaProfili(**_profil()), FirmaProfili(**_profil())
    assert a.ozet() == b.ozet()
    assert FirmaProfili(**_profil(belgeler=["ISO 9001"])).ozet() != a.ozet()
