"""LLM'siz ön filtre: açıkça uymayan (ihale, firma) çiftlerini ucuza eler. Emin değilse geçirir."""
import re
from dataclasses import dataclass, field
from datetime import date

from src.ayarlar import Ayarlar
from src.metin import icerir_mi, tl_bicimle, tr_ascii
from src.modeller import FirmaProfili, IhaleHam


@dataclass
class OnFiltreSonucu:
    gecti: bool
    nedenler: list[str] = field(default_factory=list)


def _rakam(kod: str) -> str:
    return re.sub(r"\D", "", kod)


def _faaliyet_uyar_mi(ihale: IhaleHam, profil: FirmaProfili) -> bool:
    kontroller = []
    profil_kodlari = [_rakam(k) for k in profil.okas_kodlari if _rakam(k)]
    if ihale.okas_kodlari and profil_kodlari:
        kontroller.append(any(_rakam(i).startswith(p) for i in ihale.okas_kodlari for p in profil_kodlari))
    if profil.anahtar_kelimeler:
        metin = f"{ihale.baslik} {ihale.metin}"
        kontroller.append(any(icerir_mi(metin, k) for k in profil.anahtar_kelimeler))
    return not kontroller or any(kontroller)


def on_filtre(ihale: IhaleHam, profil: FirmaProfili, bugun: date, ayarlar: Ayarlar) -> OnFiltreSonucu:
    nedenler = []
    if ihale.tur is not None and ihale.tur not in profil.ihale_turleri:
        nedenler.append(f"tür uyumsuz: {ihale.tur}")
    if profil.hizmet_illeri and ihale.il:
        if tr_ascii(ihale.il) not in {tr_ascii(il) for il in profil.hizmet_illeri}:
            nedenler.append(f"il hizmet alanı dışında: {ihale.il}")
    if not _faaliyet_uyar_mi(ihale, profil):
        nedenler.append("faaliyet alanı uyumsuz")
    if ihale.son_teklif is not None:
        if ihale.son_teklif.date() < bugun:
            nedenler.append("son teklif tarihi geçmiş")
        elif (ihale.son_teklif.date() - bugun).days < ayarlar.min_gun_kalan:
            nedenler.append(f"son teklif tarihine {ayarlar.min_gun_kalan} günden az kaldı")
    aralik = profil.tipik_ihale_buyuklugu
    maliyet = ihale.yaklasik_maliyet_tl
    if maliyet is not None:
        alt = aralik.min_tl * (1 - ayarlar.maliyet_tolerans) if aralik.min_tl is not None else None
        ust = aralik.max_tl * (1 + ayarlar.maliyet_tolerans) if aralik.max_tl is not None else None
        if (alt is not None and maliyet < alt) or (ust is not None and maliyet > ust):
            nedenler.append(f"yaklaşık maliyet tipik aralık dışında: {tl_bicimle(maliyet)}")
    return OnFiltreSonucu(gecti=not nedenler, nedenler=nedenler)
