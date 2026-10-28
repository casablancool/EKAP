"""Bir kez elle çalıştırılır: spike/ham/ altındaki gerçek EKAP yanıtlarından küçük test fikstürleri üretir.

Kullanım: python tests/fikstur/ekap_fikstur_yap.py
"""
import json
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
HAM = KOK / "spike" / "ham"
HEDEF = Path(__file__).resolve().parent / "ekap"
BT_IKN, BT_ID = "2026/1874068", "bt-ihale-id"
YAPIM_IKN = "2026/2082996"


def oku(ad: str) -> dict:
    return json.loads((HAM / ad).read_text(encoding="utf-8"))


def yaz(ad: str, veri: dict) -> None:
    (HEDEF / ad).write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    HEDEF.mkdir(parents=True, exist_ok=True)
    sayfa1 = oku("liste-2026-10-27-00000.json")["list"][:3]
    sayfa2 = oku("liste-2026-10-27-00050.json")["list"][:3]
    for oge in sayfa1 + sayfa2:
        oge["ihaleDurum"] = "2"
        oge["dokumanListe"] = []
    sayfa1[0].update(ikn=BT_IKN, id=BT_ID, ihaleAdi="CNS SİSTEMLERİ VE AĞ ALTYAPISI GÜVENLİK VE İZLEME ÇÖZÜMLERİ TEMİNİ",
                     ihaleTip="3", ihaleIlAdi="ANKARA")
    sayfa1[1].update(ikn=YAPIM_IKN, id="yapim-ihale-id", ihaleTip="2")
    sayfa2[0] = dict(sayfa1[-1], id=sayfa1[-1]["id"] + "-sayfa2")  # sayfalama kayması: aynı İKN ikinci sayfada
    yaz("liste-1.json", {"list": sayfa1, "totalCount": 6})
    yaz("liste-2.json", {"list": sayfa2, "totalCount": 6})

    for ikn in (BT_IKN, YAPIM_IKN):
        detay = oku(f"detay-{ikn.replace('/', '-')}.json")
        for ilan in detay["item"].get("ilanList") or []:
            ilan["veriHtml"] = (ilan.get("veriHtml") or "")[:3000]
        yaz(f"detay-{ikn.replace('/', '-')}.json", detay)
    for p in sorted(HEDEF.glob("*.json")):
        print(f"{p.name}: {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
