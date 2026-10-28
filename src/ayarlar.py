"""Ortam değişkenlerinden (.env) tipli ayarlar. Model kimlikleri yalnızca burada geçer."""
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# USD / 1M token (girdi, çıktı)
FIYATLAR: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

_DOGRU = {"1", "true", "evet", "yes", "on"}


@dataclass(frozen=True)
class Ayarlar:
    veri_dizini: Path = Path("veri")
    cikti_dizini: Path = Path("cikti")
    model_analiz: str = "claude-sonnet-5-5"
    model_eslestirme: str = "claude-opus-5-5"
    efor_analiz: str = "low"
    efor_eslestirme: str = "medium"
    max_tokens: int = 16000
    fiyatlar: dict[str, tuple[float, float]] = field(default_factory=lambda: dict(FIYATLAR))
    gunluk_limit_usd: float = 5.0
    min_gun_kalan: int = 3
    maliyet_tolerans: float = 0.2
    kesin_red_esigi: float = 0.25
    geri_bakis_gun: int = 3
    istek_araligi_sn: float = 2.5
    smtp_sunucu: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_kullanici: str = ""
    smtp_sifre: str = field(default="", repr=False)
    gonderen: str = ""
    yonetici_eposta: str = ""
    haftalik_bos_not: bool = False
    kaynak: str = "dosya"
    iletisim_eposta: str = ""

    @property
    def db_yolu(self) -> Path:
        return self.veri_dizini / "ekap.db"

    def fiyat(self, model: str) -> tuple[float, float]:
        if model not in self.fiyatlar:
            raise ValueError(f"fiyat tablosunda yok: {model}")
        return self.fiyatlar[model]


def ayarlari_yukle(env: Mapping[str, str] | None = None) -> Ayarlar:
    if env is None:
        load_dotenv()
        env = os.environ

    def al(ad: str, varsayilan):
        deger = env.get(ad)
        if deger is None or deger == "":
            return varsayilan
        if isinstance(varsayilan, bool):
            return deger.strip().lower() in _DOGRU
        if isinstance(varsayilan, Path):
            return Path(deger)
        return type(varsayilan)(deger)

    v = Ayarlar()
    ayarlar = Ayarlar(
        veri_dizini=al("EKAP_VERI_DIZINI", v.veri_dizini),
        cikti_dizini=al("EKAP_CIKTI_DIZINI", v.cikti_dizini),
        model_analiz=al("EKAP_MODEL_ANALIZ", v.model_analiz),
        model_eslestirme=al("EKAP_MODEL_ESLESTIRME", v.model_eslestirme),
        efor_analiz=al("EKAP_EFOR_ANALIZ", v.efor_analiz),
        efor_eslestirme=al("EKAP_EFOR_ESLESTIRME", v.efor_eslestirme),
        max_tokens=al("EKAP_MAX_TOKENS", v.max_tokens),
        gunluk_limit_usd=al("EKAP_GUNLUK_LIMIT_USD", v.gunluk_limit_usd),
        min_gun_kalan=al("EKAP_MIN_GUN_KALAN", v.min_gun_kalan),
        maliyet_tolerans=al("EKAP_MALIYET_TOLERANS", v.maliyet_tolerans),
        kesin_red_esigi=al("EKAP_KESIN_RED_ESIGI", v.kesin_red_esigi),
        geri_bakis_gun=al("EKAP_GERI_BAKIS_GUN", v.geri_bakis_gun),
        istek_araligi_sn=al("EKAP_ISTEK_ARALIGI_SN", v.istek_araligi_sn),
        smtp_sunucu=al("SMTP_SUNUCU", v.smtp_sunucu),
        smtp_port=al("SMTP_PORT", v.smtp_port),
        smtp_kullanici=al("SMTP_KULLANICI", v.smtp_kullanici),
        smtp_sifre=al("SMTP_SIFRE", v.smtp_sifre),
        gonderen=al("EKAP_GONDEREN", v.gonderen),
        yonetici_eposta=al("EKAP_YONETICI_EPOSTA", v.yonetici_eposta),
        haftalik_bos_not=al("EKAP_HAFTALIK_BOS_NOT", v.haftalik_bos_not),
        kaynak=al("EKAP_KAYNAK", v.kaynak),
        iletisim_eposta=al("EKAP_ILETISIM_EPOSTA", v.iletisim_eposta),
    )
    ayarlar.fiyat(ayarlar.model_analiz)
    ayarlar.fiyat(ayarlar.model_eslestirme)
    return ayarlar
