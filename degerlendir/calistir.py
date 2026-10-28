"""Golden set değerlendirmesi (gerçek LLM çağırır, maliyeti vardır).

Kullanım:
  python degerlendir/calistir.py [--model-analiz claude-haiku-5-5] [--model-eslestirme claude-opus-5-5]
                                 [--limit-usd 10] [--altin degerlendir/altin]
Her prompt veya model değişikliğinden önce çalıştırın. Öncelikli metrik: yanlış GİREMEZ.
"""
import argparse
import json
import sys
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from degerlendir.metrikler import (alan_hatalari, eksik_bulma_orani, karisiklik_matrisi,  # noqa: E402
                                   sinif_dogrulugu, yanlis_giremez)
from src.analiz import analiz_al  # noqa: E402
from src.ayarlar import Ayarlar, ayarlari_yukle  # noqa: E402
from src.depo import Depo  # noqa: E402
from src.eslestir import eslestir  # noqa: E402
from src.modeller import Firma, FirmaProfili, IhaleHam, Karar  # noqa: E402
from src.on_filtre import on_filtre  # noqa: E402
from src.yardimci import LimitAsildi, LLMHatasi, LLMIstemcisi  # noqa: E402


def _vaka(yol: Path, altin_dizini: Path, llm: LLMIstemcisi, ayarlar: Ayarlar) -> dict:
    veri = json.loads(yol.read_text(encoding="utf-8"))
    ihale = IhaleHam.model_validate(veri["ihale"])
    beklenen = veri["beklenen"]
    profil_yolu = Path(veri["profil"]) if veri.get("profil") else altin_dizini.parent / "profil.json"
    firma = Firma(0, FirmaProfili.model_validate_json(profil_yolu.read_text(encoding="utf-8")), True)
    bugun = ihale.yayin_tarihi or date.today()
    sonuc = {"ad": yol.stem, "ikn": ihale.ikn, "beklenen": beklenen["karar"], "tahmin": None, "neden": [],
             "eksikler": [], "alan_hatalari": [], "eksik_orani": None, "hata": None}
    try:
        filtre = on_filtre(ihale, firma.profil, bugun, ayarlar)
        if not filtre.gecti:
            sonuc.update(tahmin=Karar.GIREMEZ.value, neden=[f"ön filtre: {n}" for n in filtre.nedenler])
        else:
            analiz = analiz_al(ihale, llm.depo, llm, ayarlar, bugun)
            sonuc["alan_hatalari"] = alan_hatalari(beklenen.get("alanlar", {}), analiz)
            es = eslestir(ihale, analiz, firma, llm, ayarlar, bugun)
            sonuc.update(tahmin=es.karar.value, neden=es.gerekceler, eksikler=es.eksikler)
        sonuc["eksik_orani"] = eksik_bulma_orani(beklenen.get("eksikler", []), sonuc["eksikler"])
    except LLMHatasi as hata:
        sonuc["hata"] = str(hata)
    sonuc["maliyet_usd"] = llm.depo.baglanti.execute(
        "SELECT COALESCE(SUM(maliyet_usd), 0) FROM llm_kullanimi WHERE ikn = ?", (ihale.ikn,)).fetchone()[0]
    return sonuc


def degerlendir(altin_dizini: Path, llm: LLMIstemcisi, ayarlar: Ayarlar) -> dict:
    vakalar = []
    for yol in sorted(Path(altin_dizini).glob("*.json")):
        try:
            vakalar.append(_vaka(yol, Path(altin_dizini), llm, ayarlar))
        except LimitAsildi:
            print("Harcama limiti aşıldı; değerlendirme yarıda kesildi.", file=sys.stderr)
            break
    ciftler = [(Karar(v["beklenen"]), Karar(v["tahmin"])) for v in vakalar if v["tahmin"]]
    maliyetler = [v["maliyet_usd"] for v in vakalar]
    oranlar = [v["eksik_orani"] for v in vakalar if v["eksik_orani"] is not None]
    return {
        "matris": {b.value: {t.value: n for t, n in satir.items()} for b, satir in karisiklik_matrisi(ciftler).items()},
        "dogruluk": {k.value: d for k, d in sinif_dogrulugu(ciftler).items()},
        "yanlis_giremez": yanlis_giremez(ciftler),
        "yanlis_giremez_ikn": [v["ikn"] for v in vakalar if v["tahmin"] == Karar.GIREMEZ.value
                               and v["beklenen"] != Karar.GIREMEZ.value],
        "eksik_bulma": sum(oranlar) / len(oranlar) if oranlar else None,
        "maliyet_ihale_basi": {"ortalama": sum(maliyetler) / len(maliyetler) if maliyetler else 0.0,
                               "maks": max(maliyetler, default=0.0), "toplam": sum(maliyetler)},
        "vakalar": vakalar,
    }


def _yazdir(s: dict) -> None:
    print("Sınıf başına doğruluk:")
    for sinif, d in s["dogruluk"].items():
        print(f"  {sinif:<18} {'—' if d is None else f'%{d * 100:.0f}'}")
    print("\nKarışıklık matrisi (satır: beklenen, sütun: tahmin):")
    siniflar = list(s["matris"])
    print(" " * 20 + "".join(f"{k[:12]:>14}" for k in siniflar))
    for b in siniflar:
        print(f"  {b:<18}" + "".join(f"{s['matris'][b][t]:>14}" for t in siniflar))
    print(f"\nYanlış GİREMEZ: {s['yanlis_giremez']} {s['yanlis_giremez_ikn'] or ''}")
    print("\nÇıkarım alan hataları:")
    for v in s["vakalar"]:
        for h in v["alan_hatalari"]:
            print(f"  {v['ikn']}: {h}")
        if v["hata"]:
            print(f"  {v['ikn']}: LLM HATASI {v['hata']}")
    eb = s["eksik_bulma"]
    print(f"\nEksik bulma oranı: {'—' if eb is None else f'%{eb * 100:.0f}'}")
    m = s["maliyet_ihale_basi"]
    print(f"İhale başı maliyet: ortalama ${m['ortalama']:.4f}, maks ${m['maks']:.4f}, toplam ${m['toplam']:.4f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-analiz")
    ap.add_argument("--model-eslestirme")
    ap.add_argument("--limit-usd", type=float, default=10.0)
    ap.add_argument("--altin", default=str(KOK / "degerlendir" / "altin"))
    a = ap.parse_args()
    temel = ayarlari_yukle()
    ayarlar = replace(temel, model_analiz=a.model_analiz or temel.model_analiz,
                      model_eslestirme=a.model_eslestirme or temel.model_eslestirme, gunluk_limit_usd=a.limit_usd)
    ayarlar.fiyat(ayarlar.model_analiz)
    ayarlar.fiyat(ayarlar.model_eslestirme)

    depo = Depo(":memory:")
    sonuc = degerlendir(Path(a.altin), LLMIstemcisi(ayarlar, depo), ayarlar)
    sonuc["modeller"] = {"analiz": ayarlar.model_analiz, "eslestirme": ayarlar.model_eslestirme}
    _yazdir(sonuc)
    hedef = KOK / "degerlendir" / "sonuclar" / (
        f"{datetime.now():%Y%m%d-%H%M}-{ayarlar.model_analiz}-{ayarlar.model_eslestirme}.json")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(sonuc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSonuç dosyası: {hedef}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
