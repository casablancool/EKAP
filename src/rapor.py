"""Firma başına kısa Türkçe e-posta özeti (düz metin + HTML)."""
import html
from dataclasses import dataclass
from datetime import date, datetime

from src.metin import tl_bicimle
from src.modeller import EslesmeSonucu, IhaleHam, Karar

ALTBILGI = ("Bu e-posta karar desteği amaçlıdır. Teklif vermeden önce ilanı ve idari şartnameyi EKAP "
            "üzerinden mutlaka kontrol edin.")


@dataclass
class Ozet:
    konu: str
    metin: str
    html: str


def _tarih(t: date) -> str:
    return t.strftime("%d.%m.%Y")


def _parcalar(ihale: IhaleHam, sonuc: EslesmeSonucu) -> dict:
    sartli = sonuc.karar == Karar.SARTLI
    bilgi = [ihale.idare]
    if ihale.il:
        bilgi.append(ihale.il)
    if ihale.son_teklif:
        bilgi.append(f"Son teklif: {ihale.son_teklif:%d.%m.%Y %H:%M}")
    if ihale.yaklasik_maliyet_tl is not None:
        bilgi.append(f"Yaklaşık maliyet: {tl_bicimle(ihale.yaklasik_maliyet_tl)}")
    return {
        "baslik": f"{'⚠️ ŞARTLI' if sartli else '✅ GİREBİLİR'} · {ihale.baslik}",
        "bilgi": " · ".join(bilgi),
        "gerekceler": sonuc.gerekceler[: 2 if sartli else 3],
        "eksik": ", ".join(sonuc.eksikler) if sartli and sonuc.eksikler else None,
        "url": ihale.kaynak_url,
    }


def ihale_blogu(ihale: IhaleHam, sonuc: EslesmeSonucu) -> list[str]:
    p = _parcalar(ihale, sonuc)
    satirlar = [p["baslik"], p["bilgi"]] + [f"• {g}" for g in p["gerekceler"]]
    if p["eksik"]:
        satirlar.append(f"Eksik: {p['eksik']}")
    satirlar.append(p["url"])
    return satirlar


def _html_blogu(ihale: IhaleHam, sonuc: EslesmeSonucu) -> str:
    p = {k: html.escape(v) if isinstance(v, str) else v for k, v in _parcalar(ihale, sonuc).items()}
    maddeler = "".join(f"<li>{html.escape(g)}</li>" for g in p["gerekceler"])
    eksik = f'<p style="margin:4px 0;color:#9a5b00"><b>Eksik:</b> {p["eksik"]}</p>' if p["eksik"] else ""
    return (f'<p style="margin:0;font-weight:bold">{p["baslik"]}</p>'
            f'<p style="margin:2px 0;color:#555">{p["bilgi"]}</p>'
            f'<ul style="margin:4px 0">{maddeler}</ul>{eksik}'
            f'<p style="margin:2px 0"><a href="{p["url"]}">İlanı EKAP\'ta aç</a></p>')


def _sira(satir: tuple[IhaleHam, EslesmeSonucu]):
    ihale, sonuc = satir
    return (sonuc.karar != Karar.GIREBILIR, ihale.son_teklif is None, ihale.son_teklif or datetime.max)


def _sar(govde_metin: list[str], govde_html: list[str]) -> tuple[str, str]:
    metin = "\n\n".join(govde_metin + [ALTBILGI])
    html_govde = "".join(govde_html) + f'<p style="color:#777;font-size:12px">{html.escape(ALTBILGI)}</p>'
    return metin, f'<div style="font-family:Arial,sans-serif;font-size:14px">{html_govde}</div>'


def ozet_olustur(firma_adi: str, satirlar: list[tuple[IhaleHam, EslesmeSonucu]], uygun_olmayan_sayisi: int,
                 tarih: date) -> Ozet | None:
    uygunlar = sorted((s for s in satirlar if s[1].karar != Karar.GIREMEZ), key=_sira)
    if not uygunlar:
        return None
    n_uygun = sum(1 for _, s in uygunlar if s.karar == Karar.GIREBILIR)
    n_sartli = len(uygunlar) - n_uygun
    acilis = f"Merhaba {firma_adi}, bugün sizin için {n_uygun} uygun ve {n_sartli} şartlı ihale bulduk."

    govde_metin = [acilis] + ["\n".join(ihale_blogu(i, s)) for i, s in uygunlar]
    govde_html = [f"<p>{html.escape(acilis)}</p>", "<hr>".join(_html_blogu(i, s) for i, s in uygunlar)]
    if uygun_olmayan_sayisi > 0:
        sayi = f"{uygun_olmayan_sayisi} ihale daha incelendi, uygun değil."
        govde_metin.append(sayi)
        govde_html.append(f'<p style="color:#555">{sayi}</p>')
    metin, html_metin = _sar(govde_metin, govde_html)
    return Ozet(konu=f"EKAP: {len(uygunlar)} uygun ihale – {_tarih(tarih)}", metin=metin, html=html_metin)


def bos_hafta_notu(firma_adi: str, tarih: date) -> Ozet:
    govde = (f"Merhaba {firma_adi}, bu hafta profilinize uygun ihale çıkmadı. Profilinizde değişiklik varsa bu "
             "e-postayı yanıtlayarak bize bildirin.")
    metin, html_metin = _sar([govde], [f"<p>{html.escape(govde)}</p>"])
    return Ozet(konu=f"EKAP: bu hafta uygun ihale çıkmadı – {_tarih(tarih)}", metin=metin, html=html_metin)
