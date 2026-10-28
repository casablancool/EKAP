"""Tek ilan hata ayıklama çalıştırıcısı (gerçek LLM çağırır).

Kullanım: python calistir.py [ilanlar/x.json | ilan.txt] [--profil profil.json]
Çıktı: cikti/<ad>.json (analiz + karar) ve cikti/<ad>.txt (e-postadaki blok).
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.analiz import analiz_al
from src.ayarlar import ayarlari_yukle
from src.depo import Depo
from src.eslestir import eslestir
from src.modeller import Firma, FirmaProfili, IhaleHam
from src.rapor import ihale_blogu
from src.yardimci import LLMIstemcisi


def ilan_oku(yol: Path) -> IhaleHam:
    if yol.suffix == ".json":
        return IhaleHam.model_validate_json(yol.read_text(encoding="utf-8"))
    return IhaleHam(ikn=yol.stem, baslik=yol.stem, idare="?", metin=yol.read_text(encoding="utf-8"), kaynak_url="")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ilan", nargs="?")
    ap.add_argument("--profil", default="profil.json")
    a = ap.parse_args()
    yol = Path(a.ilan) if a.ilan else sorted(Path("ilanlar").glob("*.json"))[0]

    ayarlar = ayarlari_yukle()
    depo = Depo(":memory:")
    llm = LLMIstemcisi(ayarlar, depo)
    ihale = ilan_oku(yol)
    firma = Firma(0, FirmaProfili.model_validate_json(Path(a.profil).read_text(encoding="utf-8")), True)
    bugun = date.today()

    analiz = analiz_al(ihale, depo, llm, ayarlar, bugun)
    sonuc = eslestir(ihale, analiz, firma, llm, ayarlar, bugun)

    ayarlar.cikti_dizini.mkdir(parents=True, exist_ok=True)
    (ayarlar.cikti_dizini / f"{yol.stem}.json").write_text(json.dumps(
        {"analiz": analiz.model_dump(mode="json"), "sonuc": sonuc.model_dump(mode="json")},
        ensure_ascii=False, indent=2), encoding="utf-8")
    blok = "\n".join(ihale_blogu(ihale, sonuc))
    (ayarlar.cikti_dizini / f"{yol.stem}.txt").write_text(blok, encoding="utf-8")
    print(blok)
    print(f"\nLLM maliyeti: ${depo.bugunku_harcama_usd(bugun):.4f}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
