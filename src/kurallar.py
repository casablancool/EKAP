"""Deterministik yeterlik kuralları: LLM'siz, açıklanabilir sonuçlar.

EKAP ilanlarında iş deneyimi, iş hacmi ve banka referansı eşikleri isteklinin kendi teklif bedeline oranla
verilir; yaklaşık maliyet neredeyse hiç yayımlanmaz. Bu yüzden kural, firmanın bu ihalede verebileceği en
yüksek teklifi hesaplar ve bunu yaklaşık maliyetle (varsa) ya da firmanın tipik ihale alt sınırıyla karşılaştırır.
"""
import re

from src.ayarlar import Ayarlar
from src.metin import icerir_mi, tl_bicimle, tr_ascii
from src.modeller import FirmaProfili, IhaleAnalizi, KuralSonucu

UST_SINIR = "teklif üst sınırı"


def _buyuk_bas(s: str) -> str:
    return {"i": "İ", "ı": "I"}.get(s[0], s[0].upper()) + s[1:]


def _teklif_ust_siniri(analiz: IhaleAnalizi, profil: FirmaProfili, ayarlar: Ayarlar) -> KuralSonucu | None:
    oranlar = (analiz.is_deneyimi_orani, analiz.ciro_orani, analiz.banka_referans_orani)
    if all(o is None for o in oranlar):
        return None
    en_buyuk = max((d.tutar_tl for d in profil.is_deneyimleri), default=None)
    if analiz.is_deneyimi_orani is not None and en_buyuk is None:
        return KuralSonucu(kriter=UST_SINIR, durum="saglamaz", eksik="iş deneyim belgesi",
                           aciklama="İlan iş deneyimi istiyor, profilde iş deneyim belgesi yok.")

    adaylar = [
        ("iş deneyimi", en_buyuk, analiz.is_deneyimi_orani),
        ("iş hacmi", profil.mali.ciro_tl, analiz.ciro_orani),
        ("banka referansı", profil.mali.banka_referans_tl, analiz.banka_referans_orani),
    ]
    sinirlar = [(tutar / oran, ad) for ad, tutar, oran in adaylar if oran and oran > 0 and tutar is not None]
    if not sinirlar:
        return KuralSonucu(kriter=UST_SINIR, durum="belirsiz",
                           aciklama="teklif üst sınırı hesaplanamadı: profilde ilgili tutar yok")

    ust, sinirlayan = min(sinirlar)
    aciklama = f"{_buyuk_bas(sinirlayan)} şartına göre bu ihalede en fazla {tl_bicimle(ust)} teklif verebilirsiniz."
    maliyetten = analiz.yaklasik_maliyet_tl is not None
    ref = analiz.yaklasik_maliyet_tl if maliyetten else profil.tipik_ihale_buyuklugu.min_tl
    if ref is None:
        durum = "belirsiz"
    elif ust >= ref:
        durum = "saglar"
    elif maliyetten and ust < ayarlar.kesin_red_esigi * ref:
        durum = "kesin_red"
    else:
        durum = "saglamaz"
    eksik = f"{sinirlayan}: en fazla {tl_bicimle(ust)} teklif verilebilir" if durum == "saglamaz" else None
    return KuralSonucu(kriter=UST_SINIR, durum=durum, aciklama=aciklama, eksik=eksik)


_STANDART = re.compile(r"\b(?:iso|iec|en|ts)\s+(\d{4,5})\b")


def _standartlar(s: str) -> set[str]:
    """'TS EN ISO/IEC 27001:2022' → {'27001'}; aynı standardın farklı yazımlarını eşleştirir."""
    return set(_STANDART.findall(tr_ascii(s)))


def _belge(gereken: str, profil: FirmaProfili) -> KuralSonucu:
    var = any(icerir_mi(gereken, b) or icerir_mi(b, gereken) or (_standartlar(gereken) & _standartlar(b))
              for b in profil.belgeler)
    if var:
        return KuralSonucu(kriter=f"belge: {gereken}", durum="saglar", aciklama=f"{gereken} profilde var.")
    return KuralSonucu(kriter=f"belge: {gereken}", durum="saglamaz", aciklama=f"{gereken} profilde yok.",
                       eksik=gereken)


def kurallari_uygula(analiz: IhaleAnalizi, profil: FirmaProfili, ayarlar: Ayarlar) -> list[KuralSonucu]:
    sonuclar = []
    ust = _teklif_ust_siniri(analiz, profil, ayarlar)
    if ust is not None:
        sonuclar.append(ust)
    sonuclar.extend(_belge(b, profil) for b in analiz.yeterlik_belgeleri)
    return sonuclar
