"""Bir günlük çalışma: topla → ön filtre → analiz (önbellekli) → eşleştir → firma başına özet gönder."""
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from src.analiz import analiz_al
from src.ayarlar import Ayarlar
from src.depo import Depo
from src.eposta import DosyaGonderici, EpostaGonderici
from src.eslestir import PROMPT_SURUMU as ESLESTIRME_SURUMU
from src.eslestir import eslestir
from src.modeller import Firma, IhaleHam
from src.on_filtre import on_filtre
from src.rapor import bos_hafta_notu, ozet_olustur
from src.toplayici.kaynak import Kaynak
from src.yardimci import LimitAsildi, LLMHatasi, LLMIstemcisi

logger = logging.getLogger(__name__)


@dataclass
class CalismaOzeti:
    tarih: date
    getirilen: int = 0
    yeni: int = 0
    elenen: int = 0
    analiz_edilen: int = 0
    eslestirilen: int = 0
    gonderilen: int = 0
    atlanan_gonderim: int = 0
    hatalar: list[str] = field(default_factory=list)
    limit_asildi: bool = False
    maliyet_usd: float = 0.0
    firma_aylik_maliyet: dict[int, float] = field(default_factory=dict)

    def hata(self, mesaj: str) -> None:
        logger.error(mesaj)
        self.hatalar.append(mesaj)


def _topla(depo: Depo, kaynaklar: list[Kaynak], since: date, o: CalismaOzeti) -> None:
    for kaynak in kaynaklar:
        try:
            ihaleler = kaynak.yeni_ihaleleri_getir(since)
        except Exception as hata:
            o.hata(f"kaynak {kaynak.ad}: {hata}")
            continue
        o.getirilen += len(ihaleler)
        o.yeni += sum(depo.ihale_kaydet(i) for i in ihaleler)


def _filtrele(depo: Depo, firmalar: list[Firma], ayarlar: Ayarlar, tarih: date,
              o: CalismaOzeti) -> dict[str, tuple[IhaleHam, list[Firma]]]:
    gecenler: dict[str, tuple[IhaleHam, list[Firma]]] = {}
    for ihale in depo.islenecek_ihaleler(tarih):
        for firma in firmalar:
            oz = firma.profil.ozet()
            if depo.islendi_mi(ihale.ikn, firma.id, oz):
                continue
            try:
                sonuc = on_filtre(ihale, firma.profil, tarih, ayarlar)
            except Exception as hata:
                o.hata(f"ön filtre {ihale.ikn} / firma {firma.id}: {hata}")
                continue
            if sonuc.gecti:
                gecenler.setdefault(ihale.ikn, (ihale, []))[1].append(firma)
            else:
                logger.info("elendi %s / firma %d: %s", ihale.ikn, firma.id, "; ".join(sonuc.nedenler))
                depo.eleme_kaydet(ihale.ikn, firma.id, oz, sonuc.nedenler)
                o.elenen += 1
    return gecenler


def _analiz_ve_eslestir(depo: Depo, gecenler: dict, ayarlar: Ayarlar, llm: LLMIstemcisi, tarih: date,
                        yeniden_analiz: bool, o: CalismaOzeti) -> None:
    try:
        for ikn, (ihale, firmalar) in gecenler.items():
            onbellekte = not yeniden_analiz and depo.analiz_getir(ikn) is not None
            try:
                analiz = analiz_al(ihale, depo, llm, ayarlar, tarih, yeniden=yeniden_analiz)
            except LLMHatasi as hata:
                o.hata(str(hata))
                continue
            o.analiz_edilen += not onbellekte
            for firma in firmalar:
                try:
                    sonuc = eslestir(ihale, analiz, firma, llm, ayarlar, tarih)
                except LLMHatasi as hata:
                    o.hata(str(hata))
                    continue
                depo.eslesme_kaydet(ikn, firma.id, firma.profil.ozet(), sonuc, ayarlar.model_eslestirme,
                                    ESLESTIRME_SURUMU)
                o.eslestirilen += 1
    except LimitAsildi as hata:
        o.limit_asildi = True
        o.hata(f"analiz durduruldu: {hata}")


def _gonder(depo: Depo, firmalar: list[Firma], ayarlar: Ayarlar, gonderici: EpostaGonderici, tarih: date,
            gonder: bool, o: CalismaOzeti) -> None:
    hedef = gonderici if gonder else DosyaGonderici(ayarlar.cikti_dizini / "onizleme" / str(tarih))
    for firma in firmalar:
        if gonder and depo.gonderim_var_mi(firma.id, tarih):
            o.atlanan_gonderim += 1
            continue
        oz = firma.profil.ozet()
        try:
            satirlar = depo.gonderilmemis_eslesmeler(firma.id, oz)
            ozet = ozet_olustur(firma.profil.ad, satirlar, depo.uygun_olmayan_sayisi(firma.id, oz), tarih)
            ikn_listesi = [i.ikn for i, _ in satirlar]
            if ozet is None:
                if not (ayarlar.haftalik_bos_not and tarih.weekday() == 4
                        and not depo.hafta_gonderim_var_mi(firma.id, tarih)):
                    continue
                ozet, ikn_listesi = bos_hafta_notu(firma.profil.ad, tarih), []
            hedef.gonder(firma.profil.eposta, ozet, f"firma-{firma.id}")
        except Exception as hata:
            o.hata(f"gönderim firma {firma.id}: {hata}")
            if gonder:
                depo.gonderim_kaydet(firma.id, tarih, [], "hata", str(hata))
            continue
        if gonder:
            depo.gonderim_kaydet(firma.id, tarih, ikn_listesi, "gonderildi")
            o.gonderilen += 1


def gunluk_calistir(depo: Depo, kaynaklar: list[Kaynak], ayarlar: Ayarlar, llm: LLMIstemcisi,
                    gonderici: EpostaGonderici, tarih: date, firma_id: int | None = None, gonder: bool = True,
                    yeniden_analiz: bool = False) -> CalismaOzeti:
    o = CalismaOzeti(tarih=tarih)
    _topla(depo, kaynaklar, tarih - timedelta(days=ayarlar.geri_bakis_gun), o)
    if firma_id is None:
        firmalar = depo.firmalar()
    else:
        firma = depo.firma_getir(firma_id)
        firmalar = [firma] if firma else []
        if not firma:
            o.hata(f"firma bulunamadı: {firma_id}")
    gecenler = _filtrele(depo, firmalar, ayarlar, tarih, o)
    _analiz_ve_eslestir(depo, gecenler, ayarlar, llm, tarih, yeniden_analiz, o)
    _gonder(depo, firmalar, ayarlar, gonderici, tarih, gonder, o)
    o.maliyet_usd = depo.bugunku_harcama_usd(tarih)
    o.firma_aylik_maliyet = {f.id: depo.firma_aylik_maliyet(f.id, f"{tarih:%Y-%m}") for f in firmalar}
    logger.info("çalışma bitti:\n%s", ozet_metni(o))
    return o


def ozet_metni(o: CalismaOzeti) -> str:
    satirlar = [
        f"Çalışma özeti — {o.tarih:%d.%m.%Y}",
        f"Getirilen ihale: {o.getirilen} (yeni: {o.yeni})",
        f"Ön filtrede elenen: {o.elenen}",
        f"Analiz edilen: {o.analiz_edilen}",
        f"Eşleştirilen: {o.eslestirilen}",
        f"Gönderilen e-posta: {o.gonderilen} (bugün zaten gönderilmiş: {o.atlanan_gonderim})",
        f"Bugünkü LLM harcaması: ${o.maliyet_usd:.4f}" + (" — GÜNLÜK LİMİT AŞILDI" if o.limit_asildi else ""),
    ]
    satirlar += [f"Firma {fid}: bu ay ${m:.2f}" for fid, m in sorted(o.firma_aylik_maliyet.items())]
    if o.hatalar:
        satirlar.append(f"Hatalar ({len(o.hatalar)}):")
        satirlar += [f"  - {h}" for h in o.hatalar]
    return "\n".join(satirlar)


_KAYIT_ETIKETI = "ekap_ajan"


def kayit_kur(ayarlar: Ayarlar, tarih: date) -> Path:
    """Kök kaydediciye günlük dosya + stderr işleyicisi ekler (tekrar çağrılınca öncekileri değiştirir)."""
    dizin = ayarlar.veri_dizini / "kayitlar"
    dizin.mkdir(parents=True, exist_ok=True)
    yol = dizin / f"{tarih}.log"
    kok = logging.getLogger()
    for h in [h for h in kok.handlers if getattr(h, "name", "") == _KAYIT_ETIKETI]:
        kok.removeHandler(h)
        h.close()
    bicim = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    for h in (logging.FileHandler(yol, encoding="utf-8"), logging.StreamHandler()):
        h.set_name(_KAYIT_ETIKETI)
        h.setFormatter(bicim)
        kok.addHandler(h)
    kok.setLevel(logging.INFO)
    return yol
