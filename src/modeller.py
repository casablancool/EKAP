"""Tüm modüllerin paylaştığı veri modelleri."""
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.metin import tr_ascii

IhaleTuru = Literal["mal", "hizmet", "yapim"]
KuralDurumu = Literal["saglar", "saglamaz", "belirsiz", "kesin_red"]

_EPOSTA = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Karar(str, Enum):
    GIREBILIR = "GİREBİLİR"
    SARTLI = "ŞARTLI GİREBİLİR"
    GIREMEZ = "GİREMEZ"


class IhaleHam(BaseModel):
    ikn: str
    baslik: str
    idare: str
    il: str | None = None
    tur: IhaleTuru | None = None
    yayin_tarihi: date | None = None
    son_teklif: datetime | None = None
    yaklasik_maliyet_tl: float | None = None
    okas_kodlari: list[str] = []
    metin: str
    kaynak_url: str
    kaynak: str = "ekap"


class AralikTL(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_tl: float | None = Field(default=None, ge=0)
    max_tl: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _sira(self):
        if self.min_tl is not None and self.max_tl is not None and self.min_tl > self.max_tl:
            raise ValueError("min_tl, max_tl'den büyük olamaz")
        return self


class IsDeneyimi(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tutar_tl: float = Field(gt=0)
    yil: int = Field(ge=1990, le=2100)
    tur: str


class MaliBilgiler(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ciro_tl: float | None = Field(default=None, ge=0)
    ozkaynak_tl: float | None = Field(default=None, ge=0)
    banka_referans_tl: float | None = Field(default=None, ge=0)


class FirmaProfili(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ad: str = Field(min_length=1)
    eposta: list[str] = Field(min_length=1)
    ihale_turleri: list[IhaleTuru] = Field(min_length=1)
    anahtar_kelimeler: list[str] = []
    okas_kodlari: list[str] = []
    hizmet_illeri: list[str] = []
    tipik_ihale_buyuklugu: AralikTL = AralikTL()
    belgeler: list[str] = []
    is_deneyimleri: list[IsDeneyimi] = []
    mali: MaliBilgiler = MaliBilgiler()
    notlar: str = ""

    @field_validator("eposta")
    @classmethod
    def _eposta(cls, v: list[str]) -> list[str]:
        for adres in v:
            if not _EPOSTA.match(adres):
                raise ValueError(f"geçersiz e-posta: {adres}")
        return v

    @field_validator("ihale_turleri", mode="before")
    @classmethod
    def _turler(cls, v):
        return [tr_ascii(t) if isinstance(t, str) else t for t in v]

    def ozet(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()[:16]


class IhaleAnalizi(BaseModel):
    ozet: str
    yaklasik_maliyet_tl: float | None = None
    son_teklif_tarihi: str | None = None
    is_deneyimi_orani: float | None = None
    benzer_is_tanimi: str | None = None
    ciro_orani: float | None = None
    ozkaynak_orani: float | None = None
    banka_referans_orani: float | None = None
    yeterlik_belgeleri: list[str] = []
    diger_sartlar: list[str] = []


class KuralSonucu(BaseModel):
    kriter: str
    durum: KuralDurumu
    aciklama: str
    eksik: str | None = None


class EslesmeSonucu(BaseModel):
    karar: Karar
    gerekceler: list[str] = Field(default=[], max_length=3)
    eksikler: list[str] = []
    kurallar: list[KuralSonucu] = []


@dataclass
class Kullanim:
    model: str
    girdi_token: int
    cikti_token: int
    maliyet_usd: float


@dataclass
class Firma:
    id: int
    profil: FirmaProfili
    aktif: bool
