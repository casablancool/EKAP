from pathlib import Path

from src.modeller import FirmaProfili


def test_formda_tum_alanlar():
    form = Path("docs/musteri-profil-formu.md").read_text(encoding="utf-8")
    alanlar = list(FirmaProfili.model_fields) + [
        "tipik_ihale_buyuklugu.min_tl", "tipik_ihale_buyuklugu.max_tl",
        "mali.ciro_tl", "mali.ozkaynak_tl", "mali.banka_referans_tl",
    ]
    eksik = [a for a in alanlar if f"`{a}`" not in form]
    assert eksik == []
