"""Değerlendirme metrikleri: karar doğruluğu, karışıklık matrisi, yanlış GİREMEZ, çıkarım alan hataları."""
from src.metin import icerir_mi, tr_ascii
from src.modeller import IhaleAnalizi, Karar

Cift = tuple[Karar, Karar]  # (beklenen, tahmin)


def karisiklik_matrisi(ciftler: list[Cift]) -> dict[Karar, dict[Karar, int]]:
    matris = {b: {t: 0 for t in Karar} for b in Karar}
    for beklenen, tahmin in ciftler:
        matris[beklenen][tahmin] += 1
    return matris


def sinif_dogrulugu(ciftler: list[Cift]) -> dict[Karar, float | None]:
    sonuc = {}
    for sinif in Karar:
        ilgili = [t for b, t in ciftler if b == sinif]
        sonuc[sinif] = sum(t == sinif for t in ilgili) / len(ilgili) if ilgili else None
    return sonuc


def yanlis_giremez(ciftler: list[Cift]) -> int:
    """En kötü hata: firma girebilecekken GİREMEZ denmesi (kaçırılan ihale)."""
    return sum(1 for b, t in ciftler if b != Karar.GIREMEZ and t == Karar.GIREMEZ)


def _eslesir(a: str, b: str) -> bool:
    return icerir_mi(a, b) or icerir_mi(b, a)


def alan_hatalari(beklenen: dict, analiz: IhaleAnalizi) -> list[str]:
    hatalar = []
    for alan, bek in beklenen.items():
        bul = getattr(analiz, alan, None)
        if bek is None or isinstance(bek, (int, float)):
            dogru = bek == bul if bek is None or bul is None else abs(bul - bek) <= 0.01 * abs(bek)
        elif isinstance(bek, str):
            dogru = isinstance(bul, str) and tr_ascii(bul) == tr_ascii(bek)
        else:
            dogru = all(any(_eslesir(b, x) for x in (bul or [])) for b in bek)
        if not dogru:
            hatalar.append(f"{alan}: beklenen {bek!r}, bulunan {bul!r}")
    return hatalar


def eksik_bulma_orani(beklenen: list[str], bulunan: list[str]) -> float | None:
    if not beklenen:
        return None
    return sum(any(_eslesir(b, x) for x in bulunan) for b in beklenen) / len(beklenen)
