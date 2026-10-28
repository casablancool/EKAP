"""SQLite deposu: ihaleler, analizler, firmalar, elemeler, eşleşmeler, gönderimler, LLM kullanımı."""
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from src.modeller import EslesmeSonucu, Firma, FirmaProfili, IhaleAnalizi, IhaleHam, Karar, Kullanim

GOCLER: list[str] = [
    """
    CREATE TABLE ihaleler (
        ikn TEXT PRIMARY KEY, kaynak TEXT, son_teklif TEXT, veri_json TEXT NOT NULL, getirilme TEXT NOT NULL);
    CREATE TABLE analizler (
        ikn TEXT NOT NULL, prompt_surumu TEXT NOT NULL, model TEXT, analiz_json TEXT NOT NULL,
        girdi_token INTEGER, cikti_token INTEGER, maliyet_usd REAL, olusturma TEXT NOT NULL,
        PRIMARY KEY (ikn, prompt_surumu));
    CREATE TABLE firmalar (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT NOT NULL, profil_json TEXT NOT NULL,
        aktif INTEGER NOT NULL DEFAULT 1, olusturma TEXT NOT NULL, guncelleme TEXT NOT NULL);
    CREATE TABLE elemeler (
        ikn TEXT NOT NULL, firma_id INTEGER NOT NULL, profil_ozeti TEXT NOT NULL, nedenler_json TEXT NOT NULL,
        olusturma TEXT NOT NULL, PRIMARY KEY (ikn, firma_id, profil_ozeti));
    CREATE TABLE eslesmeler (
        ikn TEXT NOT NULL, firma_id INTEGER NOT NULL, profil_ozeti TEXT NOT NULL, karar TEXT NOT NULL,
        sonuc_json TEXT NOT NULL, model TEXT, prompt_surumu TEXT, olusturma TEXT NOT NULL,
        PRIMARY KEY (ikn, firma_id, profil_ozeti));
    CREATE TABLE gonderimler (
        firma_id INTEGER NOT NULL, tarih TEXT NOT NULL, durum TEXT NOT NULL, ikn_json TEXT NOT NULL,
        hata TEXT, zaman TEXT NOT NULL, PRIMARY KEY (firma_id, tarih));
    CREATE TABLE gonderilen_ihaleler (
        firma_id INTEGER NOT NULL, ikn TEXT NOT NULL, tarih TEXT NOT NULL, PRIMARY KEY (firma_id, ikn));
    CREATE TABLE llm_kullanimi (
        id INTEGER PRIMARY KEY AUTOINCREMENT, zaman TEXT NOT NULL, tarih TEXT NOT NULL, islem TEXT NOT NULL,
        ikn TEXT, firma_id INTEGER, model TEXT, girdi_token INTEGER, cikti_token INTEGER, maliyet_usd REAL);
    """,
]


class Depo:
    def __init__(self, yol: Path | str):
        if str(yol) != ":memory:":
            Path(yol).parent.mkdir(parents=True, exist_ok=True)
        self.baglanti = sqlite3.connect(str(yol))
        self.baglanti.row_factory = sqlite3.Row
        self._son_zaman = ""
        self._goc()

    def _goc(self) -> None:
        surum = self.baglanti.execute("PRAGMA user_version").fetchone()[0]
        for i, sql in enumerate(GOCLER[surum:], start=surum + 1):
            with self.baglanti:
                self.baglanti.executescript(sql)
                self.baglanti.execute(f"PRAGMA user_version = {i}")

    def _simdi(self) -> str:
        """Bu süreç içinde kesin artan zaman damgası (sıra karşılaştırmaları için)."""
        z = datetime.now().isoformat(timespec="microseconds")
        if z <= self._son_zaman:
            z = (datetime.fromisoformat(self._son_zaman) + timedelta(microseconds=1)).isoformat(timespec="microseconds")
        self._son_zaman = z
        return z

    def _yaz(self, sql: str, parametreler: tuple = ()) -> sqlite3.Cursor:
        with self.baglanti:
            return self.baglanti.execute(sql, parametreler)

    # --- ihaleler ---
    def ihale_kaydet(self, ihale: IhaleHam) -> bool:
        son = ihale.son_teklif.isoformat() if ihale.son_teklif else None
        imlec = self._yaz(
            "INSERT OR IGNORE INTO ihaleler (ikn, kaynak, son_teklif, veri_json, getirilme) VALUES (?, ?, ?, ?, ?)",
            (ihale.ikn, ihale.kaynak, son, ihale.model_dump_json(), self._simdi()),
        )
        return imlec.rowcount == 1

    def ihale_getir(self, ikn: str) -> IhaleHam | None:
        satir = self.baglanti.execute("SELECT veri_json FROM ihaleler WHERE ikn = ?", (ikn,)).fetchone()
        return IhaleHam.model_validate_json(satir[0]) if satir else None

    def islenecek_ihaleler(self, bugun: date) -> list[IhaleHam]:
        satirlar = self.baglanti.execute(
            "SELECT veri_json FROM ihaleler WHERE son_teklif IS NULL OR substr(son_teklif, 1, 10) >= ? ORDER BY ikn",
            (bugun.isoformat(),),
        )
        return [IhaleHam.model_validate_json(s[0]) for s in satirlar]

    # --- analizler ---
    def analiz_kaydet(self, ikn: str, analiz: IhaleAnalizi, model: str, prompt_surumu: str, kullanim: Kullanim) -> None:
        self._yaz(
            "INSERT OR REPLACE INTO analizler VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ikn, prompt_surumu, model, analiz.model_dump_json(), kullanim.girdi_token, kullanim.cikti_token,
             kullanim.maliyet_usd, self._simdi()),
        )

    def analiz_getir(self, ikn: str) -> IhaleAnalizi | None:
        satir = self.baglanti.execute(
            "SELECT analiz_json FROM analizler WHERE ikn = ? ORDER BY olusturma DESC LIMIT 1", (ikn,)
        ).fetchone()
        return IhaleAnalizi.model_validate_json(satir[0]) if satir else None

    # --- firmalar ---
    def firma_ekle(self, profil: FirmaProfili) -> int:
        z = self._simdi()
        imlec = self._yaz(
            "INSERT INTO firmalar (ad, profil_json, aktif, olusturma, guncelleme) VALUES (?, ?, 1, ?, ?)",
            (profil.ad, profil.model_dump_json(), z, z),
        )
        return imlec.lastrowid

    def firma_guncelle(self, firma_id: int, profil: FirmaProfili) -> None:
        self._yaz(
            "UPDATE firmalar SET ad = ?, profil_json = ?, guncelleme = ? WHERE id = ?",
            (profil.ad, profil.model_dump_json(), self._simdi(), firma_id),
        )

    def firma_durum(self, firma_id: int, aktif: bool) -> None:
        self._yaz("UPDATE firmalar SET aktif = ?, guncelleme = ? WHERE id = ?", (int(aktif), self._simdi(), firma_id))

    @staticmethod
    def _firma(satir: sqlite3.Row) -> Firma:
        return Firma(id=satir["id"], profil=FirmaProfili.model_validate_json(satir["profil_json"]),
                     aktif=bool(satir["aktif"]))

    def firma_getir(self, firma_id: int) -> Firma | None:
        satir = self.baglanti.execute("SELECT * FROM firmalar WHERE id = ?", (firma_id,)).fetchone()
        return self._firma(satir) if satir else None

    def firmalar(self, sadece_aktif: bool = True) -> list[Firma]:
        sql = "SELECT * FROM firmalar" + (" WHERE aktif = 1" if sadece_aktif else "") + " ORDER BY id"
        return [self._firma(s) for s in self.baglanti.execute(sql)]

    # --- elemeler ve eşleşmeler ---
    def eleme_kaydet(self, ikn: str, firma_id: int, profil_ozeti: str, nedenler: list[str]) -> None:
        self._yaz(
            "INSERT OR REPLACE INTO elemeler VALUES (?, ?, ?, ?, ?)",
            (ikn, firma_id, profil_ozeti, json.dumps(nedenler, ensure_ascii=False), self._simdi()),
        )

    def islendi_mi(self, ikn: str, firma_id: int, profil_ozeti: str) -> bool:
        parametreler = (ikn, firma_id, profil_ozeti)
        for tablo in ("elemeler", "eslesmeler"):
            if self.baglanti.execute(
                f"SELECT 1 FROM {tablo} WHERE ikn = ? AND firma_id = ? AND profil_ozeti = ?", parametreler
            ).fetchone():
                return True
        return False

    def eslesme_kaydet(self, ikn: str, firma_id: int, profil_ozeti: str, sonuc: EslesmeSonucu,
                       model: str, prompt_surumu: str) -> None:
        self._yaz(
            "INSERT OR REPLACE INTO eslesmeler VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ikn, firma_id, profil_ozeti, sonuc.karar.value, sonuc.model_dump_json(), model, prompt_surumu,
             self._simdi()),
        )

    def eslesme_getir(self, ikn: str, firma_id: int, profil_ozeti: str) -> EslesmeSonucu | None:
        satir = self.baglanti.execute(
            "SELECT sonuc_json FROM eslesmeler WHERE ikn = ? AND firma_id = ? AND profil_ozeti = ?",
            (ikn, firma_id, profil_ozeti),
        ).fetchone()
        return EslesmeSonucu.model_validate_json(satir[0]) if satir else None

    def gonderilmemis_eslesmeler(self, firma_id: int, profil_ozeti: str) -> list[tuple[IhaleHam, EslesmeSonucu]]:
        satirlar = self.baglanti.execute(
            """SELECT i.veri_json, e.sonuc_json FROM eslesmeler e JOIN ihaleler i ON i.ikn = e.ikn
               WHERE e.firma_id = ? AND e.profil_ozeti = ? AND e.karar != ?
                 AND e.ikn NOT IN (SELECT ikn FROM gonderilen_ihaleler WHERE firma_id = ?)
               ORDER BY e.ikn""",
            (firma_id, profil_ozeti, Karar.GIREMEZ.value, firma_id),
        )
        return [(IhaleHam.model_validate_json(a), EslesmeSonucu.model_validate_json(b)) for a, b in satirlar]

    def uygun_olmayan_sayisi(self, firma_id: int, profil_ozeti: str) -> int:
        son = self.baglanti.execute(
            "SELECT MAX(zaman) FROM gonderimler WHERE firma_id = ? AND durum = 'gonderildi'", (firma_id,)
        ).fetchone()[0] or ""
        eleme = self.baglanti.execute(
            "SELECT COUNT(*) FROM elemeler WHERE firma_id = ? AND profil_ozeti = ? AND olusturma > ?",
            (firma_id, profil_ozeti, son),
        ).fetchone()[0]
        giremez = self.baglanti.execute(
            "SELECT COUNT(*) FROM eslesmeler WHERE firma_id = ? AND profil_ozeti = ? AND karar = ? AND olusturma > ?",
            (firma_id, profil_ozeti, Karar.GIREMEZ.value, son),
        ).fetchone()[0]
        return eleme + giremez

    # --- gönderimler ---
    def gonderim_var_mi(self, firma_id: int, tarih: date) -> bool:
        return self.baglanti.execute(
            "SELECT 1 FROM gonderimler WHERE firma_id = ? AND tarih = ? AND durum = 'gonderildi'",
            (firma_id, tarih.isoformat()),
        ).fetchone() is not None

    def hafta_gonderim_var_mi(self, firma_id: int, tarih: date) -> bool:
        pazartesi = tarih - timedelta(days=tarih.weekday())
        return self.baglanti.execute(
            "SELECT 1 FROM gonderimler WHERE firma_id = ? AND durum = 'gonderildi' AND tarih BETWEEN ? AND ?",
            (firma_id, pazartesi.isoformat(), (pazartesi + timedelta(days=6)).isoformat()),
        ).fetchone() is not None

    def gonderim_kaydet(self, firma_id: int, tarih: date, ikn_listesi: list[str],
                        durum: Literal["gonderildi", "hata"], hata: str | None = None) -> None:
        with self.baglanti:
            self.baglanti.execute(
                "INSERT OR REPLACE INTO gonderimler VALUES (?, ?, ?, ?, ?, ?)",
                (firma_id, tarih.isoformat(), durum, json.dumps(ikn_listesi), hata, self._simdi()),
            )
            if durum == "gonderildi":
                self.baglanti.executemany(
                    "INSERT OR IGNORE INTO gonderilen_ihaleler VALUES (?, ?, ?)",
                    [(firma_id, ikn, tarih.isoformat()) for ikn in ikn_listesi],
                )

    # --- LLM kullanımı ---
    def kullanim_kaydet(self, islem: str, ikn: str, firma_id: int | None, kullanim: Kullanim, tarih: date) -> None:
        self._yaz(
            """INSERT INTO llm_kullanimi (zaman, tarih, islem, ikn, firma_id, model, girdi_token, cikti_token,
               maliyet_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self._simdi(), tarih.isoformat(), islem, ikn, firma_id, kullanim.model, kullanim.girdi_token,
             kullanim.cikti_token, kullanim.maliyet_usd),
        )

    def bugunku_harcama_usd(self, tarih: date) -> float:
        return self.baglanti.execute(
            "SELECT COALESCE(SUM(maliyet_usd), 0) FROM llm_kullanimi WHERE tarih = ?", (tarih.isoformat(),)
        ).fetchone()[0]

    def firma_aylik_maliyet(self, firma_id: int, ay: str) -> float:
        eslestirme = self.baglanti.execute(
            """SELECT COALESCE(SUM(maliyet_usd), 0) FROM llm_kullanimi
               WHERE islem = 'eslestirme' AND firma_id = ? AND substr(tarih, 1, 7) = ?""",
            (firma_id, ay),
        ).fetchone()[0]
        analiz_payi = self.baglanti.execute(
            """SELECT COALESCE(SUM(a.maliyet / f.firma_sayisi), 0) FROM
                 (SELECT ikn, SUM(maliyet_usd) AS maliyet FROM llm_kullanimi
                  WHERE islem = 'analiz' AND substr(tarih, 1, 7) = ? GROUP BY ikn) a
               JOIN (SELECT ikn, COUNT(DISTINCT firma_id) AS firma_sayisi FROM eslesmeler GROUP BY ikn) f
                 ON f.ikn = a.ikn
               WHERE a.ikn IN (SELECT ikn FROM eslesmeler WHERE firma_id = ?)""",
            (ay, firma_id),
        ).fetchone()[0]
        return eslestirme + analiz_payi
