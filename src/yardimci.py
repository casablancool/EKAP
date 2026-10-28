"""Tüm LLM çağrılarının geçtiği tek kapı: yapılandırılmış çıktı, token/maliyet kaydı, günlük limit."""
import logging
from datetime import date, datetime
from typing import Literal, TypeVar

import anthropic
import pydantic

from src.ayarlar import Ayarlar
from src.depo import Depo
from src.modeller import Kullanim

__all__ = ["Kullanim", "LLMHatasi", "LimitAsildi", "LLMIstemcisi", "maliyet_hesapla"]

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=pydantic.BaseModel)

# Ret durumunda sunucu tarafında başka modele düşme yalnızca bu modellerde var.
_FALLBACK_MODELLERI = {"claude-sonnet-5-5", "claude-opus-5-5"}


class LLMHatasi(Exception):
    """Bir ihale/eşleşme için LLM sonucu alınamadı; çağıran bu öğeyi atlar."""


class LimitAsildi(Exception):
    """Günlük LLM harcama limitine ulaşıldı; o gün başka çağrı yapılmaz."""


def maliyet_hesapla(model: str, girdi: int, cikti: int, ayarlar: Ayarlar) -> float:
    girdi_fiyat, cikti_fiyat = ayarlar.fiyat(model)
    return (girdi * girdi_fiyat + cikti * cikti_fiyat) / 1_000_000


class LLMIstemcisi:
    def __init__(self, ayarlar: Ayarlar, depo: Depo, istemci=None):
        self.ayarlar = ayarlar
        self.depo = depo
        self._istemci = istemci

    @property
    def istemci(self):
        if self._istemci is None:
            self._istemci = anthropic.Anthropic()
        return self._istemci

    def _hata_dosyasi(self, islem: str, ikn: str, icerik: str) -> None:
        self.ayarlar.cikti_dizini.mkdir(parents=True, exist_ok=True)
        ad = f"_hata_{islem}_{ikn.replace('/', '_')}_{datetime.now():%Y%m%d-%H%M%S}.txt"
        (self.ayarlar.cikti_dizini / ad).write_text(icerik, encoding="utf-8")

    def cagir(self, *, islem: Literal["analiz", "eslestirme"], model: str, efor: str, sistem: str, icerik: str,
              cikti_tipi: type[T], ikn: str, tarih: date, firma_id: int | None = None) -> tuple[T, Kullanim]:
        if self.depo.bugunku_harcama_usd(tarih) >= self.ayarlar.gunluk_limit_usd:
            raise LimitAsildi(f"günlük limit {self.ayarlar.gunluk_limit_usd} USD aşıldı")

        argumanlar = dict(
            model=model, max_tokens=self.ayarlar.max_tokens, system=sistem,
            messages=[{"role": "user", "content": icerik}],
            output_format=cikti_tipi, output_config={"effort": efor},
        )
        try:
            if model in _FALLBACK_MODELLERI:
                yanit = self.istemci.beta.messages.parse(
                    **argumanlar, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            else:
                yanit = self.istemci.messages.parse(**argumanlar)
        except (anthropic.APIError, pydantic.ValidationError) as hata:
            self._hata_dosyasi(islem, ikn, repr(hata))
            raise LLMHatasi(f"{islem} {ikn}: {hata}") from hata

        kullanim = Kullanim(model, yanit.usage.input_tokens, yanit.usage.output_tokens,
                            maliyet_hesapla(model, yanit.usage.input_tokens, yanit.usage.output_tokens, self.ayarlar))
        self.depo.kullanim_kaydet(islem, ikn, firma_id, kullanim, tarih)
        logger.info("LLM %s %s %s: %d+%d token, $%.4f", islem, ikn, model, kullanim.girdi_token,
                    kullanim.cikti_token, kullanim.maliyet_usd)

        if yanit.stop_reason in ("refusal", "max_tokens") or yanit.parsed_output is None:
            ham = "\n".join(getattr(b, "text", "") for b in yanit.content or [])
            self._hata_dosyasi(islem, ikn, f"stop_reason={yanit.stop_reason}\n\n{ham}")
            raise LLMHatasi(f"{islem} {ikn}: stop_reason={yanit.stop_reason}")
        return yanit.parsed_output, kullanim
