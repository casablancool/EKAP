"""(İhale, firma) eşleştirmesi: önce deterministik kurallar, kuralların karar veremediği kısım için LLM."""
import json
from datetime import date

from pydantic import BaseModel

from src.ayarlar import Ayarlar
from src.kurallar import UST_SINIR, kurallari_uygula
from src.metin import tr_ascii
from src.modeller import EslesmeSonucu, Firma, IhaleAnalizi, IhaleHam, Karar, KuralSonucu
from src.yardimci import LLMIstemcisi

PROMPT_SURUMU = "eslestirme-v1"

SISTEM_ISTEMI = """Sen Türk kamu ihalelerinde firmalara danışmanlık yapan bir uzmansın. Sana bir ihalenin \
çıkarılmış şartları, bir firmanın profili ve deterministik kural sonuçları verilecek. Firmanın bu ihaleye \
girip giremeyeceğine karar ver.

Kurallar:
- Kural sonuçları (teklif üst sınırı, belgeler) kesindir; sayıları yeniden hesaplama, onlarla çelişme.
- Senin işin kuralların değerlendiremediği kısım: benzer iş tanımının firmanın iş deneyimleri ve faaliyet \
alanıyla uyumu, diger_sartlar'daki şartlar.
- GİREMEZ yalnızca firmanın faaliyet alanı ihale konusuna açıkça uymuyorsa ya da bir şart belge edinerek \
veya iş ortaklığı kurarak karşılanamıyorsa verilir. Emin değilsen ŞARTLI GİREBİLİR de.
- ŞARTLI GİREBİLİR: firma eksiğini giderirse girebilir; eksikler listesine somut olarak ne gerektiğini yaz.
- gerekceler: en fazla 3 kısa Türkçe cümle, firmaya hitap eden, somut.
- Kişi adı veya telefon yazma."""


class EslesmeLLMCevabi(BaseModel):
    karar: Karar
    gerekceler: list[str]
    eksikler: list[str] = []


def _tekil(liste: list[str]) -> list[str]:
    gorulen, sonuc = set(), []
    for oge in liste:
        anahtar = tr_ascii(oge)
        if anahtar and anahtar not in gorulen:
            gorulen.add(anahtar)
            sonuc.append(oge)
    return sonuc


def kararlari_birlestir(kurallar: list[KuralSonucu], cevap: EslesmeLLMCevabi | None) -> EslesmeSonucu:
    redler = [k for k in kurallar if k.durum == "kesin_red"]
    if redler or cevap is None:
        return EslesmeSonucu(karar=Karar.GIREMEZ, gerekceler=[k.aciklama for k in redler][:3], kurallar=kurallar)
    if cevap.karar == Karar.GIREMEZ:
        return EslesmeSonucu(karar=Karar.GIREMEZ, gerekceler=cevap.gerekceler[:3], kurallar=kurallar)

    eksikler = _tekil([k.eksik for k in kurallar if k.durum == "saglamaz" and k.eksik] + cevap.eksikler)
    sartli = cevap.karar == Karar.SARTLI or bool(eksikler) or any(k.durum == "saglamaz" for k in kurallar)
    ust = [k.aciklama for k in kurallar if k.kriter == UST_SINIR]
    return EslesmeSonucu(
        karar=Karar.SARTLI if sartli else Karar.GIREBILIR,
        gerekceler=(ust + cevap.gerekceler)[:3],
        eksikler=eksikler,
        kurallar=kurallar,
    )


def _icerik(ihale: IhaleHam, analiz: IhaleAnalizi, firma: Firma, kurallar: list[KuralSonucu]) -> str:
    profil = firma.profil.model_dump(mode="json", exclude={"eposta"})
    return "\n\n".join([
        f"İHALE: {ihale.ikn} — {ihale.baslik}\nİdare: {ihale.idare}\nİl: {ihale.il or '-'}\nTür: {ihale.tur or '-'}\n"
        f"OKAS: {', '.join(ihale.okas_kodlari) or '-'}",
        "ÇIKARILMIŞ ŞARTLAR:\n" + analiz.model_dump_json(indent=2),
        "FİRMA PROFİLİ:\n" + json.dumps(profil, ensure_ascii=False, indent=2),
        "KURAL SONUÇLARI:\n" + ("\n".join(f"- {k.kriter}: {k.durum} — {k.aciklama}" for k in kurallar) or "-"),
    ])


def eslestir(ihale: IhaleHam, analiz: IhaleAnalizi, firma: Firma, llm: LLMIstemcisi, ayarlar: Ayarlar,
             tarih: date) -> EslesmeSonucu:
    kurallar = kurallari_uygula(analiz, firma.profil, ayarlar)
    if any(k.durum == "kesin_red" for k in kurallar):
        return kararlari_birlestir(kurallar, None)
    cevap, _ = llm.cagir(
        islem="eslestirme", model=ayarlar.model_eslestirme, efor=ayarlar.efor_eslestirme, sistem=SISTEM_ISTEMI,
        icerik=_icerik(ihale, analiz, firma, kurallar), cikti_tipi=EslesmeLLMCevabi, ikn=ihale.ikn, tarih=tarih,
        firma_id=firma.id,
    )
    return kararlari_birlestir(kurallar, cevap)
