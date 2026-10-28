"""Türkçe metin karşılaştırma ve TL biçimleme yardımcıları."""
import re
from decimal import ROUND_HALF_UP, Decimal

_ASCII = str.maketrans("çğıöşü", "cgiosu")


def tr_kucuk(s: str) -> str:
    """Türkçe küçük harf: I→ı, İ→i (düz .lower() 'İ'yi 'i̇' yapar)."""
    s = s.replace("I", "ı").replace("İ", "i").lower()
    return re.sub(r"\s+", " ", s).strip()


def tr_baslik(s: str) -> str:
    """Türkçe başlık harfi: 'İZMİR' → 'İzmir' (str.title() 'İzmi̇r' üretir)."""
    def kelime(k: str) -> str:
        return "-".join(p[:1] + tr_kucuk(p[1:]) for p in k.split("-"))
    return " ".join(kelime(k) for k in s.split())


def tr_ascii(s: str) -> str:
    """Karşılaştırma anahtarı: Türkçe küçük harf, aksansız, noktalama yerine boşluk."""
    s = tr_kucuk(s).translate(_ASCII)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def icerir_mi(metin: str, aranan: str) -> bool:
    anahtar = tr_ascii(aranan)
    return bool(anahtar) and anahtar in tr_ascii(metin)


def tl_bicimle(tutar: float) -> str:
    tam = int(Decimal(str(tutar)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{tam:,}".replace(",", ".") + " TL"
