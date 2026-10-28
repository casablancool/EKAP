# Plan 2 — EKAP İhale Ajanı Çekirdek Hat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the whole unattended daily pipeline: store → pre-filter → cached extraction → multi-firm matching → short Turkish digest → email. Around it go the admin CLI, the eval script and VPS scheduling. Tenders come from a local-file source until the EKAP collector (Plan 3) plugs into the same `Kaynak` protocol.

**Architecture:** A `src/` package with one module per pipeline unit. All modules share the pydantic models in `src/modeller.py` and one SQLite `Depo`. `src/calisma.py` runs one day; `yonet.py` is the single entry point for both the admin and the timer. Every LLM call goes through `LLMIstemcisi` in `src/yardimci.py`, which uses structured outputs, records tokens and cost in the DB, and enforces the daily cap. Tests inject a fake Anthropic client.

**Tech Stack:** Python 3.12, `anthropic` SDK (`messages.parse` with a pydantic `output_format`), `pydantic` v2, `python-dotenv`, stdlib `sqlite3` / `smtplib` / `argparse` / `logging`, `pytest`. Production runs on a Linux VPS with a systemd timer; CI runs on GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-28-ekap-ihale-ajani-design.md` (decisions in §9). Preceded by `docs/superpowers/plans/2026-10-28-plan1-ekap-erisim-spike.md`.

## Global Constraints

- Turkish identifiers for modules, functions and user-facing text. Customer-facing output is Turkish only.
- Must run on Windows/PowerShell and Linux: use `pathlib`, and open every file with `encoding="utf-8"`.
- Runtime dependencies are only `anthropic`, `pydantic` and `python-dotenv`; the dev dependency is `pytest`. Exact `==` pins go in `requirements.txt` / `requirements-dev.txt`.
- Secrets live only in `.env` or the server environment. `.env`, `veri/` and `cikti/` are gitignored. The API key is read by the SDK from `ANTHROPIC_API_KEY` and is never stored on `Ayarlar` or logged.
- Model IDs appear only in `src/ayarlar.py`: `claude-sonnet-5-5` (extraction default), `claude-opus-5-5` (matching default), `claude-haiku-5-5` (candidate). Never add date suffixes.
- Unit tests never call the real API. Real calls happen only in `degerlendir/calistir.py` and `calistir.py`.
- One tender's or one firm's failure never stops the run. It is logged, added to `CalismaOzeti.hatalar` and skipped.
- The pre-filter is recall-first: an unknown field never drops a tender.
- At most one successful digest per firm per date. A tender is never listed twice to the same firm. No empty digests, except the opt-in weekly note.
- KVKK: contact persons' names and phones never go into structured fields or emails. The digest renders only `IhaleHam` header fields and match results, never `metin`.

## Review Focus

1. **Turkish casing in matching:** "İSTANBUL", "Istanbul", "ISPARTA" and "Iğdır" must match profile entries "istanbul", "ısparta" and "igdir". Plain `.lower()` turns "İ" into "i̇" and breaks the match. Pinned in Task 2 (`test_tr_kucuk_noktali_i`) and Task 6 (`test_il_turkce_harf`).
2. **Profile edited after matches exist:** after `firma duzenle`, that firm's unsent tenders must be filtered and matched again against the new profile. A stale "GİREMEZ" from the old profile must not hide them. Pinned in Task 3 (`test_eslesme_profil_degisince_yok`) and Task 13 (`test_profil_degisince_yeniden_eslestirilir`).
3. **Same tender on consecutive days:** with a 3-day look-back, yesterday's tenders come back today. They must not be re-sent or re-analysed. Pinned in Task 13 (`test_ertesi_gun_ayni_ihale_tekrar_gonderilmez`).
4. **Tenders with missing fields:** no yaklaşık maliyet, no OKAS, no deadline or no il (this is common on EKAP). The tender passes the filter, the rules report "belirsiz", and the digest omits the cost line instead of printing "None". Pinned in Tasks 6, 9 and 11.
5. **One firm's SMTP failure:** a bad address or a Gmail rejection. The other firms still get their digests, the failure is stored as `hata`, it is retried on the next run that day, and the admin is alerted. Pinned in Task 13 (`test_smtp_hatasi_digerlerini_durdurmaz_ve_tekrar_dener`).

## File Structure

```
ekap-ajan/
  requirements.txt, requirements-dev.txt, pytest.ini, .gitignore, .env.example
  .github/workflows/test.yml      CI: pytest on ubuntu + windows
  profil.json                     sample firm profile (network/IT firm, Ankara)
  ilanlar/*.json                  local tender files in IhaleHam shape (DosyaKaynagi input)
  calistir.py                     single-tender debug runner (real LLM)
  yonet.py                        admin CLI + timer entry point
  src/
    ayarlar.py                    Ayarlar (env → typed config, price table)
    metin.py                      Turkish normalisation, TL formatting
    modeller.py                   all pydantic models + Karar enum + Firma
    depo.py                       SQLite store, migrations, every query
    toplayici/kaynak.py           Kaynak protocol, KaynakHatasi
    toplayici/dosya_kaynagi.py    DosyaKaynagi (reads ilanlar/)
    on_filtre.py                  cheap per-(tender, firm) filter
    yardimci.py                   LLMIstemcisi, Kullanim, cost, cap, _hata files
    analiz.py                     extraction prompt + cached analiz_al
    kurallar.py                   deterministic eligibility rules
    eslestir.py                   rules + LLM → EslesmeSonucu
    rapor.py                      short digest (text + HTML)
    eposta.py                     SMTP / file senders, admin alert
    calisma.py                    one daily run + summary + logging setup
  degerlendir/
    calistir.py, metrikler.py, profil.json, altin/*.json, altin/README.md, sonuclar/
  dagitim/ekap-ajan.service, dagitim/ekap-ajan.timer, dagitim/yedekle.sh
  docs/musteri-profil-formu.md    Turkish intake form + answer → field mapping
  README.md                       Turkish operations guide
  tests/sahte.py                  FakeIstemci, FakeKaynak, KayitGonderici
  tests/test_*.py
```

---

### Task 1: Project scaffold and settings

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `pytest.ini` (`testpaths = tests`, `pythonpath = .`), `.env.example`, `src/__init__.py`, `src/ayarlar.py`, `tests/test_ayarlar.py`, `.github/workflows/test.yml`
- Create or extend: `.gitignore` (keep `spike/ham/` from Plan 1; add `.env`, `veri/`, `cikti/`, `.venv/`, `__pycache__/`)

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Ayarlar` and `ayarlari_yukle(env: Mapping[str, str] | None = None) -> Ayarlar`. With `None`, it calls `load_dotenv()` and then reads `os.environ`. Also `Ayarlar.fiyat(model: str) -> tuple[float, float]`, which returns USD per 1M input/output tokens and raises `ValueError("fiyat tablosunda yok: <model>")`.

Fields (env var → default):

| field | env | default |
|---|---|---|
| `veri_dizini` / `cikti_dizini` | `EKAP_VERI_DIZINI` / `EKAP_CIKTI_DIZINI` | `Path("veri")` / `Path("cikti")` |
| `db_yolu` | — | `veri_dizini / "ekap.db"` |
| `model_analiz` / `model_eslestirme` | `EKAP_MODEL_ANALIZ` / `EKAP_MODEL_ESLESTIRME` | `claude-sonnet-5-5` / `claude-opus-5-5` |
| `efor_analiz` / `efor_eslestirme` | `EKAP_EFOR_ANALIZ` / `EKAP_EFOR_ESLESTIRME` | `low` / `medium` |
| `max_tokens` | `EKAP_MAX_TOKENS` | `16000` |
| `fiyatlar` | — | `{"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00), "claude-opus-5-5": (4.00, 20.00)}` |
| `gunluk_limit_usd` | `EKAP_GUNLUK_LIMIT_USD` | `5.0` |
| `min_gun_kalan` | `EKAP_MIN_GUN_KALAN` | `3` |
| `maliyet_tolerans` | `EKAP_MALIYET_TOLERANS` | `0.2` |
| `kesin_red_esigi` | `EKAP_KESIN_RED_ESIGI` | `0.25` |
| `geri_bakis_gun` | `EKAP_GERI_BAKIS_GUN` | `3` |
| `istek_araligi_sn` | `EKAP_ISTEK_ARALIGI_SN` | `2.5` |
| `smtp_sunucu`, `smtp_port`, `smtp_kullanici`, `smtp_sifre` (`repr=False`), `gonderen` | `SMTP_SUNUCU`, `SMTP_PORT`, `SMTP_KULLANICI`, `SMTP_SIFRE`, `EKAP_GONDEREN` | `smtp.gmail.com`, `587`, `""`, `""`, `""` |
| `yonetici_eposta` | `EKAP_YONETICI_EPOSTA` | `""` |
| `haftalik_bos_not` | `EKAP_HAFTALIK_BOS_NOT` | `False` (accepts `1/true/evet`) |
| `kaynak` | `EKAP_KAYNAK` | `dosya` |

`ayarlari_yukle` raises `ValueError` if either configured model is missing from `fiyatlar`.

- [ ] **Step 1: Write the failing tests** in `tests/test_ayarlar.py`:
  - `test_varsayilanlar`: `a = ayarlari_yukle({})` → `a.model_analiz == "claude-sonnet-5-5"`, `a.model_eslestirme == "claude-opus-5-5"`, `a.gunluk_limit_usd == 5.0`, `a.min_gun_kalan == 3`, `a.haftalik_bos_not is False`
  - `test_env_ezer`: `{"EKAP_MODEL_ANALIZ": "claude-haiku-5-5", "EKAP_GUNLUK_LIMIT_USD": "2", "EKAP_HAFTALIK_BOS_NOT": "evet"}` → `"claude-haiku-5-5"`, `2.0`, `True`
  - `test_sifre_repr_gizli`: `"gizli123" not in repr(ayarlari_yukle({"SMTP_SIFRE": "gizli123"}))`
  - `test_bilinmeyen_model`: `{"EKAP_MODEL_ANALIZ": "claude-x"}` → `pytest.raises(ValueError, match="fiyat tablosunda yok")`
- [ ] **Step 2:** Run `pytest tests/test_ayarlar.py -v`. Expected: FAIL (`ModuleNotFoundError: src.ayarlar`).
- [ ] **Step 3:** Implement `src/ayarlar.py` per the table. Write `.env.example` with every env var above plus `ANTHROPIC_API_KEY=`, all with empty or default values.
- [ ] **Step 4:** Run `pytest -v`. Expected: 4 passed.
- [ ] **Step 5:** Pin dependencies. Run `pip install anthropic pydantic python-dotenv pytest`, then write the exact versions from `pip freeze` for those packages into `requirements.txt` (first three) and `requirements-dev.txt` (`-r requirements.txt` + pytest).
- [ ] **Step 6:** Write `.github/workflows/test.yml`. On push/PR, use a matrix of `ubuntu-latest` and `windows-latest` with Python 3.12, run `pip install -r requirements-dev.txt`, then `pytest -q`. Do not set any secrets.
- [ ] **Step 7: Commit**: `git add -A; git commit -m "feat: proje iskeleti ve ayarlar"`

### Task 2: Shared models, Turkish text helpers and sample profile

**Files:**
- Create: `src/metin.py`, `src/modeller.py`, `profil.json`, `tests/test_metin.py`, `tests/test_modeller.py`

**Interfaces:**
- Produces, in `src/metin.py`:
  - `tr_kucuk(s: str) -> str`: maps `I→ı` and `İ→i` before `.lower()`, then strips and collapses whitespace.
  - `tr_ascii(s: str) -> str`: `tr_kucuk`, then `ç→c ğ→g ı→i ö→o ş→s ü→u`, then punctuation becomes spaces and whitespace is collapsed.
  - `icerir_mi(metin: str, aranan: str) -> bool`: `tr_ascii(aranan)` is a substring of `tr_ascii(metin)`; an empty `aranan` gives `False`.
  - `tl_bicimle(tutar: float) -> str`: rounds half-up to whole TL, uses `.` as the thousands separator and appends `" TL"`.
- Produces, in `src/modeller.py`:
  - `IhaleTuru = Literal["mal", "hizmet", "yapim"]`
  - `class Karar(str, Enum)`: `GIREBILIR = "GİREBİLİR"`, `SARTLI = "ŞARTLI GİREBİLİR"`, `GIREMEZ = "GİREMEZ"`
  - `IhaleHam(BaseModel)`: `ikn: str`, `baslik: str`, `idare: str`, `il: str | None = None`, `tur: IhaleTuru | None = None`, `yayin_tarihi: date | None = None`, `son_teklif: datetime | None = None`, `yaklasik_maliyet_tl: float | None = None`, `okas_kodlari: list[str] = []`, `metin: str`, `kaynak_url: str`, `kaynak: str = "ekap"`
  - `AralikTL(min_tl: float | None = None, max_tl: float | None = None)`: validator `min_tl <= max_tl` when both are set
  - `IsDeneyimi(tutar_tl: float (>0), yil: int (1990–2100), tur: str)`
  - `MaliBilgiler(ciro_tl, ozkaynak_tl, banka_referans_tl: float | None = None, each ≥ 0)`
  - `FirmaProfili(BaseModel, extra="forbid")`: `ad: str` (min 1), `eposta: list[str]` (min 1, each must match `^[^@\s]+@[^@\s]+\.[^@\s]+$`), `ihale_turleri: list[IhaleTuru]` (min 1; a before-validator passes each item through `tr_ascii`, so "Yapım" becomes "yapim"), `anahtar_kelimeler: list[str] = []`, `okas_kodlari: list[str] = []`, `hizmet_illeri: list[str] = []`, `tipik_ihale_buyuklugu: AralikTL = AralikTL()`, `belgeler: list[str] = []`, `is_deneyimleri: list[IsDeneyimi] = []`, `mali: MaliBilgiler = MaliBilgiler()`, `notlar: str = ""`; method `ozet() -> str` returns the first 16 hex characters of the sha256 of `model_dump_json()`
  - `IhaleAnalizi(BaseModel)`: `ozet: str`, `yaklasik_maliyet_tl: float | None`, `son_teklif_tarihi: str | None` (ISO), `is_deneyimi_orani: float | None`, `benzer_is_tanimi: str | None`, `ciro_orani: float | None`, `ozkaynak_orani: float | None`, `banka_referans_orani: float | None`, `yeterlik_belgeleri: list[str] = []`, `diger_sartlar: list[str] = []`. Ratios are fractions (%50 → 0.5).
  - `KuralDurumu = Literal["saglar", "saglamaz", "belirsiz", "kesin_red"]`; `KuralSonucu(kriter: str, durum: KuralDurumu, aciklama: str, eksik: str | None = None)`
  - `EslesmeSonucu(karar: Karar, gerekceler: list[str] (max 3), eksikler: list[str] = [], kurallar: list[KuralSonucu] = [])`
  - `@dataclass Firma(id: int, profil: FirmaProfili, aktif: bool)`

- [ ] **Step 1: Write the failing tests.**
  - `test_metin.py`:
    - `test_tr_kucuk_noktali_i`: `tr_kucuk("İSTANBUL") == "istanbul"`, `tr_kucuk("ISPARTA") == "ısparta"`, `tr_ascii("Iğdır") == "igdir"`, `tr_ascii("İZMİR") == "izmir"`
    - `test_icerir_mi`: `icerir_mi("AĞ ALTYAPISI Kurulumu", "ağ altyapısı")` is `True`; `icerir_mi("x", "")` is `False`
    - `test_tl_bicimle`: `1250000` → `"1.250.000 TL"`, `999.5` → `"1.000 TL"`, `0` → `"0 TL"`
  - `test_modeller.py`:
    - `test_ornek_profil_gecerli`: `FirmaProfili.model_validate_json(Path("profil.json").read_text(encoding="utf-8"))`
    - `test_yapim_normalize`: `ihale_turleri=["Yapım"]` → `["yapim"]`
    - `test_aralik_ters`: min 5_000_000, max 1_000_000 → `ValidationError` whose message contains `tipik_ihale_buyuklugu`
    - `test_bilinmeyen_alan`: an extra key `"telefon"` → `ValidationError`
    - `test_eposta_gecersiz`: `["firma.com"]` → `ValidationError`
    - `test_profil_ozeti`: two equal profiles give the same `ozet()`; adding one `belgeler` item changes it
- [ ] **Step 2:** Run `pytest tests/test_metin.py tests/test_modeller.py -v`. Expected: FAIL (import errors).
- [ ] **Step 3:** Implement `src/metin.py` and `src/modeller.py` per the Interfaces block.
- [ ] **Step 4:** Write `profil.json`: a network/IT firm in Ankara with types `["mal", "hizmet"]`, keywords such as "ağ altyapısı", "yapısal kablolama", "network", "switch", 2 OKAS prefixes, `hizmet_illeri` `["Ankara", "Kırıkkale", "Konya"]`, a tipik range of 500 000–15 000 000 TL, `belgeler` `["TS EN ISO 9001", "TSE Hizmet Yeterlilik Belgesi"]` (deliberately **no** Yetkili Satıcı Belgesi), two experience documents and a full `mali` block.
- [ ] **Step 5:** Run `pytest -v`. Expected: all pass.
- [ ] **Step 6: Commit**: `git commit -am "feat: ortak modeller, Türkçe metin yardımcıları, örnek profil"` (add the new files first)

### Task 3: SQLite store

**Files:**
- Create: `src/depo.py`, `tests/test_depo.py`

**Interfaces:**
- Consumes: Task 2 models.
- Produces: `class Depo`. `Depo(yol: Path | str)` creates parent directories; `":memory:"` works for tests. It sets `row_factory = sqlite3.Row` and runs migrations through `PRAGMA user_version`. The module-level `GOCLER: list[str]` lists the migrations in order. Methods:
  - `ihale_kaydet(ihale: IhaleHam) -> bool` (True if new; `INSERT OR IGNORE`)
  - `ihale_getir(ikn) -> IhaleHam | None`
  - `islenecek_ihaleler(bugun: date) -> list[IhaleHam]` (`son_teklif` is null or ≥ bugun)
  - `analiz_kaydet(ikn, analiz: IhaleAnalizi, model: str, prompt_surumu: str, kullanim: Kullanim) -> None`
  - `analiz_getir(ikn) -> IhaleAnalizi | None` (newest row of any `prompt_surumu`)
  - `firma_ekle(profil) -> int`, `firma_guncelle(firma_id, profil) -> None`, `firma_durum(firma_id, aktif: bool) -> None`, `firma_getir(firma_id) -> Firma | None`, `firmalar(sadece_aktif: bool = True) -> list[Firma]`
  - `eleme_kaydet(ikn, firma_id, profil_ozeti, nedenler: list[str])`
  - `islendi_mi(ikn, firma_id, profil_ozeti) -> bool` (a row exists in `elemeler` or `eslesmeler`)
  - `eslesme_kaydet(ikn, firma_id, profil_ozeti, sonuc: EslesmeSonucu, model: str, prompt_surumu: str)`
  - `eslesme_getir(ikn, firma_id, profil_ozeti) -> EslesmeSonucu | None`
  - `gonderilmemis_eslesmeler(firma_id, profil_ozeti) -> list[tuple[IhaleHam, EslesmeSonucu]]` (karar ≠ GİREMEZ, ikn not in `gonderilen_ihaleler` for this firm)
  - `uygun_olmayan_sayisi(firma_id, profil_ozeti) -> int`: GİREMEZ matches plus eliminations created after this firm's last `gonderildi` send (or all of them if it has none)
  - `gonderim_var_mi(firma_id, tarih: date) -> bool` (status `gonderildi`)
  - `hafta_gonderim_var_mi(firma_id, tarih: date) -> bool` (any `gonderildi` in the ISO week of `tarih`)
  - `gonderim_kaydet(firma_id, tarih, ikn_listesi: list[str], durum: Literal["gonderildi", "hata"], hata: str | None = None)`: upserts on (firma_id, tarih); on `gonderildi` it also inserts each ikn into `gonderilen_ihaleler`
  - `kullanim_kaydet(islem: str, ikn: str, firma_id: int | None, kullanim: Kullanim, tarih: date)`
  - `bugunku_harcama_usd(tarih: date) -> float`
  - `firma_aylik_maliyet(firma_id: int, ay: str) -> float` (`ay` = `"YYYY-MM"`)
- `Kullanim` is imported from `src/yardimci.py` (Task 7). To avoid a circular import, define `Kullanim` in `src/modeller.py` in this task (`@dataclass Kullanim(model: str, girdi_token: int, cikti_token: int, maliyet_usd: float)`) and have `yardimci` re-export it.

Tables in migration 1 (all timestamps ISO text):
- `ihaleler(ikn PK, kaynak, veri_json, getirilme)`
- `analizler(ikn, prompt_surumu, model, analiz_json, girdi_token, cikti_token, maliyet_usd, olusturma, PK(ikn, prompt_surumu))`
- `firmalar(id INTEGER PK AUTOINCREMENT, ad, profil_json, aktif, olusturma, guncelleme)`
- `elemeler(ikn, firma_id, profil_ozeti, nedenler_json, olusturma, PK(ikn, firma_id, profil_ozeti))`
- `eslesmeler(ikn, firma_id, profil_ozeti, karar, sonuc_json, model, prompt_surumu, olusturma, PK(ikn, firma_id, profil_ozeti))`
- `gonderimler(firma_id, tarih, durum, ikn_json, hata, zaman, PK(firma_id, tarih))`
- `gonderilen_ihaleler(firma_id, ikn, tarih, PK(firma_id, ikn))`
- `llm_kullanimi(id PK, zaman, tarih, islem, ikn, firma_id, model, girdi_token, cikti_token, maliyet_usd)`

Per-firm monthly cost algorithm: the sum of this firm's `eslestirme` costs in the month, plus, for each tender this firm has an `eslesmeler` row for, that tender's `analiz` cost in the month divided by the number of distinct firms with an `eslesmeler` row for it.

- [ ] **Step 1: Write the failing tests** in `tests/test_depo.py`, using small builders `ornek_ihale(ikn, **degisiklik)` and `ornek_profil(**degisiklik)` in `tests/sahte.py`:
  - `test_ihale_tekrar_kaydi`: first save is `True`, second is `False`; one row
  - `test_analiz_onbellek_son_surum`: save `analiz-v1`, then `analiz-v2` → `analiz_getir` returns the v2 content; an unknown ikn gives `None`
  - `test_firma_ekle_listele_durdur`: two firms; after `firma_durum(2, False)`, `firmalar()` has ids `[1]` and `firmalar(False)` has `[1, 2]`
  - `test_eslesme_profil_degisince_yok`: saved under ozet `"a"` → `eslesme_getir(..., "a")` is not `None`, `(..., "b")` is `None`, and `islendi_mi(..., "b")` is `False`
  - `test_gonderilmemis_eslesmeler`: GİREBİLİR for X and GİREMEZ for Y → only X returned; after `gonderim_kaydet(1, d, ["X"], "gonderildi")` → `[]`
  - `test_gonderim_hata_sonra_basari`: `hata` → `gonderim_var_mi` is `False`; then `gonderildi` the same day → `True`
  - `test_bugunku_harcama`: 0.5 + 0.25 today and 1.0 yesterday → `pytest.approx(0.75)`
  - `test_firma_aylik_maliyet`: analysis of X costs 0.30; firms 1 and 2 both matched X; firm 1 matching costs 0.10 → firm 1 = `approx(0.25)`, firm 2 = `approx(0.15)`
  - `test_goc_iki_kez`: `Depo(tmp_path / "e.db")` twice → no error, `PRAGMA user_version` == `len(GOCLER)`
  - `test_uygun_olmayan_sayisi`: 2 eliminations + 1 GİREMEZ → 3; after a `gonderildi` send, newer rows only
- [ ] **Step 2:** Run `pytest tests/test_depo.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `Kullanim` in `src/modeller.py`, then `src/depo.py`.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: SQLite depo ve göçler`

### Task 4: Admin CLI — firm and profile commands

**Files:**
- Create: `yonet.py`, `tests/test_yonet.py`

**Interfaces:**
- Consumes: `Depo`, `FirmaProfili`, `ayarlari_yukle`.
- Produces: `ana(argv: list[str] | None = None, depo: Depo | None = None) -> int` (exit code; argparse subcommands; `if __name__ == "__main__": sys.exit(ana())`). Task 13 adds `calistir` and `rapor-onizle` to the same parser.
  - `firma ekle --dosya F` prints `Firma eklendi: <id> <ad>`
  - `firma listele` prints a table with `id  ad  durum(aktif|durduruldu)  eposta`
  - `firma goster <id> [--dosya F]` prints the profile JSON (`indent=2`, `ensure_ascii=False`) or writes it to F; used to edit a profile
  - `firma duzenle <id> --dosya F`
  - `firma durdur <id>` / `firma aktif <id>`
  - `firma sablon` prints an empty profile JSON with every field
  - `profil dogrula <dosya>` prints `Profil geçerli.` (exit 0), or one line per error as `<alan.yolu>: <mesaj>` on stderr (exit 1)
  - A missing firm id prints `Firma bulunamadı: <id>` (exit 1)

- [ ] **Step 1: Write the failing tests** (`capsys`, `Depo(":memory:")` passed in):
  - `test_firma_ekle_ve_listele`: exit 0; the listing contains `1`, the profile name and `aktif`
  - `test_firma_ekle_gecersiz`: an inverted range file → exit 1, stderr contains `tipik_ihale_buyuklugu`; `firmalar(False) == []`
  - `test_firma_durdur_aktif`: after `durdur`, the listing shows `durduruldu`; after `aktif`, it shows `aktif`
  - `test_firma_duzenle`: after `duzenle` with a changed `ad`, `firma_getir(1).profil.ad` is the new name
  - `test_profil_dogrula`: valid → `Profil geçerli.`, exit 0; invalid e-mail → exit 1
  - `test_sablon_alanlari`: `json.loads(output).keys() == FirmaProfili.model_fields.keys()`
  - `test_bilinmeyen_firma`: `firma durdur 99` → exit 1, `Firma bulunamadı: 99`
- [ ] **Step 2:** Run `pytest tests/test_yonet.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `yonet.py`. When `depo` is `None`, use `Depo(ayarlari_yukle().db_yolu)`. Write the JSON output with `ensure_ascii=False`, and call `sys.stdout.reconfigure(encoding="utf-8")` at startup so Turkish prints correctly in PowerShell.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass. Demo: `python yonet.py firma ekle --dosya profil.json; python yonet.py firma listele`
- [ ] **Step 5: Commit**: `feat: yönetim CLI firma/profil komutları`

### Task 5: Source protocol and local file source

**Files:**
- Create: `src/toplayici/__init__.py`, `src/toplayici/kaynak.py`, `src/toplayici/dosya_kaynagi.py`, `tests/test_dosya_kaynagi.py`
- Create: `ilanlar/ornek-*.json` if Plan 1 did not produce samples. Add 3 hand-made samples marked `"kaynak": "ornek"`: an IT network tender in Ankara that requires a Yetkili Satıcı Belgesi, a yapım tender, and a hizmet tender in İzmir.

**Interfaces:**
- Produces:
  - `class Kaynak(Protocol)`: `ad: str`; `def yeni_ihaleleri_getir(self, since: date) -> list[IhaleHam]: ...`
  - `class KaynakHatasi(Exception)`
  - `class DosyaKaynagi`: `__init__(self, dizin: Path)`, `ad = "dosya"`. It reads `dizin/*.json` in sorted order and returns those whose `yayin_tarihi` is ≥ since or `None`. An invalid file is logged with `logger.warning("bozuk ilan dosyası atlandı: %s", yol)` and skipped. A missing directory raises `KaynakHatasi`.

- [ ] **Step 1: Write the failing tests:**
  - `test_gecerli_dosyalar`: 2 valid files in `tmp_path` → 2 `IhaleHam`
  - `test_bozuk_dosya_atlanir`: 1 valid + 1 `{"ikn": 1` → 1 result; `caplog.text` contains the bad file's name
  - `test_since_filtresi`: yayin 2026-10-20 and 2026-10-27, since 2026-10-25 → only the 27th; `yayin_tarihi=None` is kept
  - `test_dizin_yok`: → `pytest.raises(KaynakHatasi)`
  - `test_ornek_ilanlar_gecerli`: every `ilanlar/*.json` in the repo loads
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement the source.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: Kaynak protokolü ve dosya kaynağı`

### Task 6: Pre-filter

**Files:**
- Create: `src/on_filtre.py`, `tests/test_on_filtre.py`

**Interfaces:**
- Consumes: `IhaleHam`, `FirmaProfili`, `Ayarlar`, `metin.tr_ascii` / `icerir_mi` / `tl_bicimle`.
- Produces: `@dataclass OnFiltreSonucu(gecti: bool, nedenler: list[str])` and `on_filtre(ihale: IhaleHam, profil: FirmaProfili, bugun: date, ayarlar: Ayarlar) -> OnFiltreSonucu`. Every failing rule is collected, and `gecti = not nedenler`.

Rules and their exact reason strings:
1. `ihale.tur` is set and not in `profil.ihale_turleri` → `"tür uyumsuz: {tur}"`
2. `profil.hizmet_illeri` is non-empty, `ihale.il` is set, and `tr_ascii(il)` is not among the normalised profile provinces → `"il hizmet alanı dışında: {il}"`
3. Field of activity. The code check applies when both the tender's and the profile's OKAS lists are non-empty; it passes if a tender code, with non-digits removed, starts with a profile code with non-digits removed. The keyword check applies when the profile has keywords; it passes if any keyword `icerir_mi(baslik + " " + metin)`. Drop with `"faaliyet alanı uyumsuz"` only if at least one check applies and **every** check that applies fails.
4. `son_teklif` is set: if its date is < bugun → `"son teklif tarihi geçmiş"`; else if `(son_teklif.date() - bugun).days < min_gun_kalan` → `"son teklif tarihine {min_gun_kalan} günden az kaldı"`
5. `yaklasik_maliyet_tl` is set and the profile range has a bound: if it is < `min_tl × (1 − maliyet_tolerans)` or > `max_tl × (1 + maliyet_tolerans)` → `"yaklaşık maliyet tipik aralık dışında: {tl_bicimle(x)}"`

- [ ] **Step 1: Write the failing tests** (parametrised, bugun = 2026-10-28, default `Ayarlar`):
  - `test_tur`: `None` passes; `"yapim"` vs `["mal", "hizmet"]` drops with `"tür uyumsuz: yapim"`
  - `test_il_turkce_harf`: `"İSTANBUL"` vs `["istanbul"]` passes; `"Iğdır"` vs `["Igdir"]` passes; `"İzmir"` vs `["Ankara"]` drops; empty `hizmet_illeri` passes; `il=None` passes
  - `test_faaliyet`: codes `["32420000-3"]` vs `["3242"]` pass; `["45000000"]` vs `["3242"]` with no keyword in the text drops; no codes with keyword "ağ altyapısı" and text "AĞ ALTYAPISI yenileme" passes; mismatched codes but a keyword present passes; a profile with neither codes nor keywords passes
  - `test_son_teklif`: bugun+2 days drops (`"3 günden az"`); bugun+3 passes; yesterday gives `"son teklif tarihi geçmiş"`; `None` passes
  - `test_maliyet`: 900 000 vs min 1 000 000 passes (tolerance); 700 000 drops; `None` passes; a profile without a range passes
  - `test_birden_cok_neden`: type and province both wrong → `len(nedenler) == 2`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `on_filtre`.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: ön filtre (recall öncelikli)`

### Task 7: LLM call helper, cost and daily cap

**Files:**
- Create: `src/yardimci.py`, `tests/test_yardimci.py`
- Modify: `tests/sahte.py` (add `FakeIstemci`, `fake_cevap`)

**Interfaces:**
- Consumes: `Ayarlar`, `Depo.kullanim_kaydet` / `bugunku_harcama_usd`, `Kullanim`.
- Produces:
  - `class LLMHatasi(Exception)`, `class LimitAsildi(Exception)`
  - `maliyet_hesapla(model: str, girdi: int, cikti: int, ayarlar: Ayarlar) -> float`
  - `class LLMIstemcisi`: `__init__(self, ayarlar: Ayarlar, depo: Depo, istemci=None)` (default `anthropic.Anthropic()`, created lazily on first call so tests and `--help` need no key), and
    `cagir(self, *, islem: Literal["analiz", "eslestirme"], model: str, efor: str, sistem: str, icerik: str, cikti_tipi: type[T], ikn: str, tarih: date, firma_id: int | None = None) -> tuple[T, Kullanim]`
- `tests/sahte.py` → `FakeIstemci(cevaplar: Callable[[dict], object])` exposes `.messages.parse(**kw)` and `.beta.messages.parse(**kw)`, records every call's kwargs in `.cagrilar`, and returns `SimpleNamespace(parsed_output=..., stop_reason="end_turn", usage=SimpleNamespace(input_tokens=..., output_tokens=...), content=[])`. Helper: `fake_cevap(nesne, girdi=1000, cikti=200, stop_reason="end_turn")`.

Behaviour of `cagir`, in order:
1. If `depo.bugunku_harcama_usd(tarih) >= ayarlar.gunluk_limit_usd`, raise `LimitAsildi`. The client is not called.
2. Build the arguments: `model`, `max_tokens=ayarlar.max_tokens`, `system=sistem`, `messages=[{"role": "user", "content": icerik}]`, `output_format=cikti_tipi`, `output_config={"effort": efor}`. For `claude-sonnet-5-5` and `claude-opus-5-5`, call `istemci.beta.messages.parse(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")` (refusal fallback). Otherwise call `istemci.messages.parse(...)`. Before writing this, check the exact shape against the claude-api skill's Python docs.
3. If a response arrives, always record usage with `depo.kullanim_kaydet` and log `"LLM %s %s %s: %d+%d token, $%.4f"`.
4. If `stop_reason` is `refusal` or `max_tokens`, or `parsed_output` is `None`, or any `anthropic.APIError` / `pydantic.ValidationError` is raised, write `cikti_dizini / f"_hata_{islem}_{ikn-with-/-replaced-by-_}_{YYYYmmdd-HHMMSS}.txt"` (the response's text blocks, or `repr(exc)`), then raise `LLMHatasi`. The SDK keeps its default 2 retries.

- [ ] **Step 1: Write the failing tests:**
  - `test_maliyet_hesapla`: haiku with 1 000 000 + 1 000 000 tokens → `approx(0.60)`; sonnet with 1000 + 200 → `approx(0.004)`
  - `test_basarili_cagri`: returns `(parsed, Kullanim)`; `depo.bugunku_harcama_usd(d) == approx(0.004)`
  - `test_limit_asildi`: 5.0 already spent → `LimitAsildi`, `fake.cagrilar == []`
  - `test_ret_hata_dosyasi`: `stop_reason="refusal"` → `LLMHatasi`; a `_hata_analiz_2026_1_*.txt` file exists in `tmp_path`; usage is still recorded
  - `test_zaman_asimi`: the fake raises `anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com"))` → `LLMHatasi`
  - `test_fallback_parametreleri`: a sonnet call goes through `beta.messages.parse` with `fallbacks == "default"`; a haiku call goes through `messages.parse` without `fallbacks`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `src/yardimci.py`, re-exporting `Kullanim` from `modeller`.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: LLM çağrı yardımcısı, maliyet kaydı ve günlük limit`

### Task 8: Extraction (cached)

**Files:**
- Create: `src/analiz.py`, `tests/test_analiz.py`

**Interfaces:**
- Consumes: `LLMIstemcisi.cagir`, `Depo.analiz_getir` / `analiz_kaydet`, `IhaleAnalizi`.
- Produces: `PROMPT_SURUMU = "analiz-v1"`, `SISTEM_ISTEMI: str`, `analiz_icerigi(ihale: IhaleHam) -> str`, and `analiz_al(ihale: IhaleHam, depo: Depo, llm: LLMIstemcisi, ayarlar: Ayarlar, tarih: date, yeniden: bool = False) -> IhaleAnalizi`. It returns the cached analysis unless `yeniden` is set; otherwise it calls `cagir(islem="analiz", model=ayarlar.model_analiz, efor=ayarlar.efor_analiz, ...)` and saves the result with `PROMPT_SURUMU`.

`SISTEM_ISTEMI` (Turkish) must say:
- Use only what the text says; a missing value is `null`, never a guess.
- Ratios are fractions (%25 → 0.25) of the bidder's **teklif edilen bedel**. For `ciro_orani`, use the "toplam ciro" ratio when the text offers alternatives. A ratio relative to anything else (e.g. a balance-sheet ratio) does not belong in these fields.
- `yaklasik_maliyet_tl` only when the text states a yaklaşık maliyet amount (rare).
- `yeterlik_belgeleri` lists only certificates and authorisation documents the bidder must **hold** (e.g. TSE, ISO 9001, Yetkili Satıcı Belgesi, Yetki Belgesi), not standard bid forms (teklif mektubu, geçici teminat, …).
- `benzer_is_tanimi` is the "benzer iş" definition, quoted short.
- Never copy contact persons' names or phone numbers.
- `ozet` is one Turkish sentence.

`analiz_icerigi` = the header lines (İKN, başlık, idare, il, tür, OKAS) + `"\n\n"` + `metin`, with no truncation.

- [ ] **Step 1: Write the failing tests:**
  - `test_onbellekten_doner`: analysis already stored → returned, `fake.cagrilar == []`
  - `test_yeni_analiz_kaydedilir`: → one call with `model == "claude-sonnet-5-5"`; a stored row with `prompt_surumu == "analiz-v1"`; the call's `messages[0]["content"]` contains `ihale.metin`
  - `test_yeniden`: cached and `yeniden=True` → one call; `analiz_getir` returns the new content
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `src/analiz.py`.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: önbellekli ihale analizi`

### Task 9: Deterministic eligibility rules

**Files:**
- Create: `src/kurallar.py`, `tests/test_kurallar.py`

**Interfaces:**
- Consumes: `IhaleAnalizi`, `FirmaProfili`, `KuralSonucu`, `Ayarlar.kesin_red_esigi`, `metin.icerir_mi` / `tl_bicimle`.
- Produces: `kurallari_uygula(analiz: IhaleAnalizi, profil: FirmaProfili, ayarlar: Ayarlar) -> list[KuralSonucu]`

Background (spike report §6): EKAP announcements give experience, turnover and bank-reference thresholds as a share of **the bidder's own bid** ("teklif edilen bedelin %25'inden az olmamak üzere"), and yaklaşık maliyet is almost never published. So the rules compute **the highest bid the firm can make** (`teklif üst sınırı`) and compare it with a reference amount.

Criteria (`kriter` names exact):
- `"teklif üst sınırı"`. It is emitted only when at least one of `is_deneyimi_orani`, `ciro_orani` or `banka_referans_orani` is set. Steps:
  1. Collect the limits:
     - `"iş deneyimi"`: `en_buyuk / is_deneyimi_orani`, where `en_buyuk` is the largest `is_deneyimleri.tutar_tl`
     - `"iş hacmi"`: `mali.ciro_tl / ciro_orani`
     - `"banka referansı"`: `mali.banka_referans_tl / banka_referans_orani`
     
     A limit is only collected when its ratio > 0 and the profile value is set.
  2. If `is_deneyimi_orani` is set and the firm has no experience documents → `saglamaz`, eksik `"iş deneyim belgesi"`. Stop here.
  3. If no limit was collected → `belirsiz`, aciklama `"teklif üst sınırı hesaplanamadı: profilde ilgili tutar yok"`.
  4. `ust = min(limits)`; `sinirlayan` = the name of the smallest limit.
  5. aciklama is always `f"{sinirlayan.capitalize()} şartına göre bu ihalede en fazla {tl_bicimle(ust)} teklif verebilirsiniz."` (for example "İş hacmi şartına göre …").
  6. Reference `ref`: `yaklasik_maliyet_tl` if set, else `profil.tipik_ihale_buyuklugu.min_tl`.
     - `ref` is `None` → `belirsiz`.
     - `ust >= ref` → `saglar`.
     - `ust < kesin_red_esigi × ref` **and** `ref` came from `yaklasik_maliyet_tl` → `kesin_red`.
     - Otherwise → `saglamaz`, eksik `f"{sinirlayan}: en fazla {tl_bicimle(ust)} teklif verilebilir"`.
     
     The firm's own typical size can never cause `kesin_red` (recall first).
- Özkaynak criteria in announcements are balance-sheet ratios (öz kaynak / toplam aktif), which the profile cannot check. They are left to the LLM, and there is no deterministic özkaynak rule.
- One `"belge: {ad}"` per `yeterlik_belgeleri` item: `saglar` if any held document `icerir_mi` the required one or the other way round; otherwise `saglamaz` with eksik = the required name.

- [ ] **Step 1: Write the failing tests:**
  - `test_teklif_ust_siniri_ciro_sinirlar`: experience ratio 0.25 with largest document 6 000 000 (limit 24M); ciro ratio 0.25 with ciro 2 000 000 (limit 8M); tipik min 5 000 000 → `saglar`; aciklama `"İş hacmi şartına göre bu ihalede en fazla 8.000.000 TL teklif verebilirsiniz."`
  - `test_teklif_ust_siniri_tipik_buyukluk_alti`: same, tipik min 10 000 000 → `saglamaz`, eksik `"iş hacmi: en fazla 8.000.000 TL teklif verilebilir"`
  - `test_kesin_red_yalnizca_yaklasik_maliyetle`: limit 8M with yaklaşık maliyet 40 000 000 → `kesin_red`; limit 8M with no cost and tipik min 40 000 000 → `saglamaz`
  - `test_referans_yok`: no cost and no tipik range → `belirsiz`, and the aciklama still contains `"8.000.000 TL"`
  - `test_deneyim_belgesi_yok`: experience ratio set, no documents → `saglamaz`, eksik `"iş deneyim belgesi"`
  - `test_oran_yok`: all three ratios `None` → no `"teklif üst sınırı"` result
  - `test_belgeler`: required "Yetkili Satıcı Belgesi" with held ["TS EN ISO 9001"] → `saglamaz`, eksik "Yetkili Satıcı Belgesi"; required "ISO 9001 Kalite Yönetim Sistemi Belgesi" with held ["ISO 9001"] → `saglar`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement the rules.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: deterministik yeterlik kuralları`

### Task 10: Matching

**Files:**
- Create: `src/eslestir.py`, `tests/test_eslestir.py`

**Interfaces:**
- Consumes: `kurallari_uygula`, `LLMIstemcisi.cagir`, `Firma`, `IhaleHam`, `IhaleAnalizi`.
- Produces:
  - `PROMPT_SURUMU = "eslestirme-v1"`, `SISTEM_ISTEMI: str`
  - `class EslesmeLLMCevabi(BaseModel)`: `karar: Karar`, `gerekceler: list[str]` (1–3), `eksikler: list[str] = []`
  - `kararlari_birlestir(kurallar: list[KuralSonucu], cevap: EslesmeLLMCevabi | None) -> EslesmeSonucu`
  - `eslestir(ihale: IhaleHam, analiz: IhaleAnalizi, firma: Firma, llm: LLMIstemcisi, ayarlar: Ayarlar, tarih: date) -> EslesmeSonucu`. It runs the rules; if any is `kesin_red`, it combines with `None` and makes no LLM call. Otherwise it calls `cagir(islem="eslestirme", model=ayarlar.model_eslestirme, efor=ayarlar.efor_eslestirme, firma_id=firma.id, ...)`. The content is the tender header, `analiz.model_dump_json()`, the profile JSON **without `eposta`**, and the rule results.

`kararlari_birlestir` algorithm, in order:
1. Any `kesin_red` → GİREMEZ; gerekceler = those rules' `aciklama`, first 3.
2. `cevap.karar == GİREMEZ` → GİREMEZ with `cevap.gerekceler[:3]`.
3. eksikler = the `eksik` of each `saglamaz` rule, then `cevap.eksikler`, de-duplicated by `tr_ascii` with order kept.
4. Any `saglamaz`, or `cevap.karar == ŞARTLI`, or non-empty eksikler → ŞARTLI.
5. Otherwise GİREBİLİR. gerekceler = the `"teklif üst sınırı"` rule's aciklama first (when that rule exists), then `cevap.gerekceler`, capped at 3. `kurallar` is always attached.

`SISTEM_ISTEMI` (Turkish) must say:
- The numeric rule results are authoritative; don't recompute them.
- Judge field fit (`benzer_is_tanimi` vs the firm's experience and activities) and `diger_sartlar`.
- Answer GİREMEZ only when the firm's field clearly doesn't fit or a requirement can't be met by obtaining a document or partnering.
- Give at most 3 short Turkish reasons and make each eksik concrete.

- [ ] **Step 1: Write the failing tests:**
  - `test_birlestir` (parametrised): kesin_red + `None` → GİREMEZ; all saglar + LLM GİREBİLİR → GİREBİLİR; belge saglamaz + LLM GİREBİLİR → ŞARTLI with eksik `["Yetkili Satıcı Belgesi"]`; LLM GİREMEZ → GİREMEZ; a duplicate eksik in a different case ("yetkili satici belgesi") is kept once; 5 LLM reasons → 3
  - `test_kesin_red_llm_cagirmaz`: → `fake.cagrilar == []`
  - `test_eposta_llme_gitmez`: the profile e-mail does not appear in the call's content
  - `test_referans_vaka`: `profil.json` plus an analysis requiring "Yetkili Satıcı Belgesi" (no cost, experience ratio 0.25) with a fake LLM answering GİREBİLİR → ŞARTLI; eksik contains "Yetkili Satıcı Belgesi"; `"teklif üst sınırı"` is `saglar`; the first gerekçe starts with "İş deneyimi şartına göre" or "İş hacmi şartına göre"
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `src/eslestir.py`.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: kural + LLM eşleştirme`

### Task 11: Short digest and debug runner

**Files:**
- Create: `src/rapor.py`, `tests/test_rapor.py`, `calistir.py`

**Interfaces:**
- Consumes: `IhaleHam`, `EslesmeSonucu`, `Karar`, `tl_bicimle`.
- Produces: `@dataclass Ozet(konu: str, metin: str, html: str)`, `ihale_blogu(ihale: IhaleHam, sonuc: EslesmeSonucu) -> list[str]` (text lines), `ozet_olustur(firma_adi: str, satirlar: list[tuple[IhaleHam, EslesmeSonucu]], uygun_olmayan_sayisi: int, tarih: date) -> Ozet | None`, and `bos_hafta_notu(firma_adi: str, tarih: date) -> Ozet`.

Exact copy (dates `gg.aa.yyyy`, deadlines `gg.aa.yyyy SS:dd`):
- Subject: `f"EKAP: {n_uygun + n_sartli} uygun ihale – {tarih}"`
- Opening: `f"Merhaba {firma_adi}, bugün sizin için {n_uygun} uygun ve {n_sartli} şartlı ihale bulduk."`
- Block lines:
  1. `"✅ GİREBİLİR · {baslik}"` or `"⚠️ ŞARTLI · {baslik}"`
  2. `" · ".join([idare, il?, "Son teklif: …"?, "Yaklaşık maliyet: …"?])`, leaving out any part that is `None`
  3. Bullets `"• {gerekçe}"`: at most 3 for GİREBİLİR, at most 2 for ŞARTLI
  4. ŞARTLI only: `"Eksik: " + ", ".join(eksikler)`
  5. `kaynak_url`
- After the blocks, if `uygun_olmayan_sayisi > 0`: `f"{k} ihale daha incelendi, uygun değil."`
- Footer: `"Bu e-posta karar desteği amaçlıdır. Teklif vermeden önce ilanı ve idari şartnameyi EKAP üzerinden mutlaka kontrol edin."`
- Weekly note subject: `f"EKAP: bu hafta uygun ihale çıkmadı – {tarih}"`; body: `f"Merhaba {firma_adi}, bu hafta profilinize uygun ihale çıkmadı. Profilinizde değişiklik varsa bu e-postayı yanıtlayarak bize bildirin."` + footer.
- Ordering: GİREBİLİR before ŞARTLI; inside each, `son_teklif` ascending with `None` last. GİREMEZ entries in `satirlar` are ignored. If no GİREBİLİR/ŞARTLI remain, return `None`.
- The HTML version holds the same content: `html.escape` on every field, the link as `<a href>`, blocks separated by `<hr>`, inline styles only.

- [ ] **Step 1: Write the failing tests:**
  - `test_bos_ise_none`: `[]` → `None`; only GİREMEZ → `None`
  - `test_siralama`: ŞARTLI due 30.10, GİREBİLİR due 15.11, GİREBİLİR due 05.11 → title order 05.11, 15.11, then ŞARTLI
  - `test_sartli_eksik`: the text contains `"Eksik: Yetkili Satıcı Belgesi"`
  - `test_eksik_alanlar`: `yaklasik_maliyet_tl=None` and `il=None` → no `"Yaklaşık maliyet"`, no `"None"`
  - `test_blok_satir_sayisi`: 5 reasons → `len(ihale_blogu(...)) <= 6` for both decisions
  - `test_html_kacis`: baslik `"A & B <x>"` → `"&amp;"` in html and `"<x>"` not in html
  - `test_uygun_olmayan`: 12 → `"12 ihale daha incelendi, uygun değil."`; 0 → that line is absent
  - `test_kisisel_veri_yok`: `metin` containing "İrtibat: Ahmet Yılmaz 0312 000 00 00" → "Ahmet" is in neither text nor html
  - `test_konu`: 2 matches → subject `"EKAP: 2 uygun ihale – 28.10.2026"`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `src/rapor.py`.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass.
- [ ] **Step 5:** Write `calistir.py`: `python calistir.py [ilan] [--profil profil.json]`. The default ilan is the first file in `ilanlar/`. A `.json` file loads as `IhaleHam`; a `.txt` file becomes `IhaleHam(ikn=<stem>, baslik=<stem>, idare="?", metin=<text>, kaynak_url="")`. It uses an in-memory `Depo` and the real `LLMIstemcisi`, runs `analiz_al` + `eslestir`, writes `cikti/<stem>.json` (analysis + result) and `cikti/<stem>.txt` (the lines of `ihale_blogu`), and prints the `.txt` contents. There is no unit test because it makes real LLM calls. Demo: `python calistir.py ilanlar/<network tender>.json`; the expected decision is ŞARTLI with the missing Yetkili Satıcı Belgesi.
- [ ] **Step 6: Commit**: `feat: kısa özet ve tek ilan çalıştırıcı`

### Task 12: Email senders and admin alert

**Files:**
- Create: `src/eposta.py`, `tests/test_eposta.py`

**Interfaces:**
- Consumes: `Ozet`, `Ayarlar`.
- Produces:
  - `class EpostaGonderici(Protocol)`: `def gonder(self, alicilar: list[str], ozet: Ozet, etiket: str) -> None` (`etiket` such as `"firma-3"` is used only for file names and logs)
  - `class SmtpGonderici(ayarlar)`: builds an `EmailMessage` with `set_content(metin)` + `add_alternative(html, subtype="html")`, From = `ayarlar.gonderen`, To = comma-joined. Port 465 uses `smtplib.SMTP_SSL`; any other port uses `smtplib.SMTP` + `starttls()`. It logs in with `smtp_kullanici` / `smtp_sifre` (timeout 30 s) and raises on failure.
  - `class DosyaGonderici(dizin: Path)`: writes `dizin/{etiket}.txt` and `.html`, plus `alicilar` and `konu` as the first lines of the `.txt`
  - `yonetici_uyar(gonderici: EpostaGonderici, ayarlar: Ayarlar, konu: str, metin: str) -> None`: sends `Ozet(f"[ekap-ajan] {konu}", metin, f"<pre>{html.escape(metin)}</pre>")` to `[ayarlar.yonetici_eposta]` with etiket `"yonetici"`. It never raises: any exception is logged with `logger.exception`. With an empty `yonetici_eposta`, it only logs.

- [ ] **Step 1: Write the failing tests** (monkeypatch `smtplib.SMTP` / `SMTP_SSL` with a recording fake):
  - `test_mesaj_iki_parcali`: content type `multipart/alternative`; the text part contains "Eksik"; the Subject header decodes to the Turkish subject unchanged
  - `test_port_587_starttls` and `test_port_465_ssl`
  - `test_dosya_gonderici`: `firma-1.txt` and `firma-1.html` exist and are UTF-8
  - `test_yonetici_uyar_hata_yutar`: the sender raises → no exception, and `caplog` has the error
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `src/eposta.py`.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: e-posta gönderimi ve yönetici uyarısı`

### Task 13: Daily run, run summary, `calistir` / `rapor-onizle` commands

**Files:**
- Create: `src/calisma.py`, `tests/test_calisma.py`
- Modify: `yonet.py`, `tests/test_yonet.py`, `tests/sahte.py` (add `FakeKaynak(ihaleler, hata=None)` and `KayitGonderici(basarisiz_alicilar=set())`, which records `(alicilar, ozet, etiket)`)

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `@dataclass CalismaOzeti`: `tarih: date`, `getirilen=0`, `yeni=0`, `elenen=0`, `analiz_edilen=0`, `eslestirilen=0`, `gonderilen=0`, `atlanan_gonderim=0`, `hatalar: list[str]`, `limit_asildi=False`, `maliyet_usd=0.0`, `firma_aylik_maliyet: dict[int, float]`
  - `gunluk_calistir(depo, kaynaklar: list[Kaynak], ayarlar, llm: LLMIstemcisi, gonderici: EpostaGonderici, tarih: date, firma_id: int | None = None, gonder: bool = True, yeniden_analiz: bool = False) -> CalismaOzeti`
  - `ozet_metni(o: CalismaOzeti) -> str`: Turkish, one line per counter, then `"Bugünkü LLM harcaması: $x.xxxx"`, then `"Firma <id>: bu ay $x.xx"` per firm, then the errors
  - `kayit_kur(ayarlar, tarih) -> Path`: root logger to `veri_dizini/kayitlar/{tarih}.log` (UTF-8) and stderr, format `%(asctime)s %(levelname)s %(name)s: %(message)s`

`gunluk_calistir` algorithm:
1. Fetch: `since = tarih - timedelta(days=geri_bakis_gun)`. For each source, wrap the call in try/except `Exception`; on failure, append `f"kaynak {k.ad}: {exc}"` and continue. `depo.ihale_kaydet` each tender and count `getirilen` / `yeni`.
2. `firmalar`: the active ones, or `[firma_getir(firma_id)]`. `adaylar = depo.islenecek_ihaleler(tarih)`.
3. For each tender × firm with `oz = firma.profil.ozet()`: skip if `islendi_mi`. Run `on_filtre`; on failure, `eleme_kaydet` and count `elenen`; otherwise add to `gecenler[ikn]`.
4. For each ikn in `gecenler`: `analiz_al(..., yeniden=yeniden_analiz)` (count only real calls). `LLMHatasi` → append to hatalar, drop the ikn. `LimitAsildi` → set `limit_asildi=True` and leave steps 4–5 entirely.
5. For each (ikn, firma) still in `gecenler`: `eslestir` → `eslesme_kaydet`. `LLMHatasi` → hata, skip. `LimitAsildi` → as above.
6. For each firm, with sender = `gonderici` if `gonder` else `DosyaGonderici(cikti_dizini / "onizleme" / str(tarih))`:
   - If `gonder` and `gonderim_var_mi(firma, tarih)`, count `atlanan_gonderim` and move on.
   - Build `satirlar = gonderilmemis_eslesmeler(firma.id, oz)` and the digest with `ozet_olustur(..., uygun_olmayan_sayisi(firma.id, oz), tarih)`.
   - If the digest is `None`: when `haftalik_bos_not` is on, `tarih.weekday() == 4` and `not hafta_gonderim_var_mi`, use `bos_hafta_notu` with an empty ikn list; otherwise move on.
   - Send with `etiket=f"firma-{firma.id}"`. Wrap rendering and sending in try/except. On success with `gonder`, call `gonderim_kaydet(..., "gonderildi")` and count `gonderilen`. On failure, call `gonderim_kaydet(..., "hata", str(exc))` and append to hatalar. In dry-run mode, never write to `gonderimler`.
7. Set `maliyet_usd = bugunku_harcama_usd(tarih)` and `firma_aylik_maliyet` for each firm for `tarih`'s month.

`yonet.py` additions:
- `calistir [--tarih YYYY-MM-DD] [--firma ID] [--gonderme] [--yeniden-analiz]`:
  - Calls `kayit_kur`, then builds the source from `ayarlar.kaynak` (`"dosya"` → `DosyaKaynagi(Path("ilanlar"))`; Plan 3 adds `"ekap"`), the `LLMIstemcisi` and the `SmtpGonderici`.
  - Wraps everything in try/except `Exception`. On an unexpected error it calls `yonetici_uyar(..., "çalışma başarısız", traceback.format_exc())` and returns 2.
  - After the run it prints `ozet_metni`. If there are hatalar or `limit_asildi`, it calls `yonetici_uyar(..., "çalışma uyarısı", ozet_metni(o))` and returns 1; otherwise it returns 0.
  - `ana()` gains `gonderici` and `kaynaklar` keyword parameters for tests.
- `rapor-onizle <firma_id> [--tarih]`: makes no LLM call and no fetch. It renders from the stored matches with `DosyaGonderici`, prints the file path, or prints `Gösterilecek uygun ihale yok.`

- [ ] **Step 1: Write the failing tests** in `tests/test_calisma.py`. Use `Depo(":memory:")`, `FakeIstemci` (returns an `IhaleAnalizi` when `output_format is IhaleAnalizi`, else `EslesmeLLMCevabi(karar=GİREBİLİR, gerekceler=["uygun"])`), `FakeKaynak` and `KayitGonderici`, with `tarih = date(2026, 10, 28)` (a Wednesday) and tenders due 2026-11-10:
  - `test_uctan_uca_gonderir`: 2 fitting tenders, 1 firm → 1 email to the profile address; `gonderim_var_mi` is `True`; the summary shows `yeni == 2`, `analiz_edilen == 2`, `eslestirilen == 2`, `gonderilen == 1`
  - `test_ayni_gun_tekrar_calisma`: run twice → 1 email in total; `len(fake.cagrilar)` unchanged after the 2nd run; `atlanan_gonderim == 1`
  - `test_ertesi_gun_ayni_ihale_tekrar_gonderilmez`: 2nd run on 2026-10-29 with the same tenders → no new email
  - `test_analiz_bir_kez_coklu_firma`: 2 firms, 1 tender → 1 analiz call, 2 eslestirme calls, 2 emails
  - `test_bir_ihale_hatasi_calismayi_durdurmaz`: refusal for tender A only → B is emailed; hatalar contains A's ikn
  - `test_kaynak_hatasi_devam`: source 1 raises, source 2 works → an email is sent; hatalar contains `"kaynak"`
  - `test_limit_asilinca_analiz_durur`: limit 0.0001 → `limit_asildi`; no LLM calls after the first; no exception
  - `test_smtp_hatasi_digerlerini_durdurmaz_ve_tekrar_dener`: 2 firms, firm 1's address fails → firm 2 is sent; firm 1 has a `hata` row; a 2nd run the same day with a working sender → firm 1 is sent and firm 2 is skipped
  - `test_profil_degisince_yeniden_eslestirilir`: run, then `firma_guncelle` with a changed `notlar`, then run with `tarih` +1 → the eslestirme call count increases; no tender that was already sent is re-sent
  - `test_gonderme_kapali_dosyaya_yazar`: `gonder=False` → the file `cikti/onizleme/2026-10-28/firma-1.html` exists; `gonderim_var_mi` is `False`; `KayitGonderici` is empty
  - `test_haftalik_bos_not`: no fitting tenders on Friday 2026-10-30 → no email by default; with `haftalik_bos_not=True`, 1 email whose subject contains "bu hafta uygun ihale çıkmadı"
  - `test_elenen_kaydedilir`: a yapım tender for a mal-only firm → `elenen == 1`; no LLM call; it is counted in the next digest's "ihale daha incelendi"
  - In `tests/test_yonet.py`: `test_calistir_beklenmeyen_hata`: monkeypatch `gunluk_calistir` to raise → exit 2; the admin sender got a subject containing "çalışma başarısız"
- [ ] **Step 2:** Run `pytest tests/test_calisma.py tests/test_yonet.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `src/calisma.py`, then extend `yonet.py`.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass. Demo:
  - `python yonet.py calistir --gonderme` writes the preview to `cikti/onizleme/<tarih>/`
  - `python yonet.py rapor-onizle 1`
- [ ] **Step 5: Commit**: `feat: günlük çalışma, özet, calistir ve rapor-onizle komutları`

### Task 14: Evaluation

**Files:**
- Create: `degerlendir/metrikler.py`, `degerlendir/calistir.py`, `degerlendir/profil.json` (copy of `profil.json`), `degerlendir/altin/README.md`, `degerlendir/altin/*.json` (seed cases), `degerlendir/sonuclar/.gitkeep`, `tests/test_metrikler.py`

**Interfaces:**
- Consumes: `on_filtre`, `analiz_al`, `eslestir`, `LLMIstemcisi`, `Depo(":memory:")`.
- Golden case file: `{"ihale": IhaleHam, "beklenen": {"karar": "<Karar value>", "eksikler": [..], "alanlar": {<IhaleAnalizi field>: value, ...}}, "profil": "<optional path; default degerlendir/profil.json>", "not": "<why this label>"}`
- Produces, in `degerlendir/metrikler.py`:
  - `karisiklik_matrisi(ciftler: list[tuple[Karar, Karar]]) -> dict[Karar, dict[Karar, int]]` (expected → predicted)
  - `sinif_dogrulugu(ciftler) -> dict[Karar, float | None]` (recall per expected class; `None` if the class is absent)
  - `yanlis_giremez(ciftler) -> int` (expected ≠ GİREMEZ, predicted == GİREMEZ)
  - `alan_hatalari(beklenen: dict, analiz: IhaleAnalizi) -> list[str]`. Numbers use a 1 % relative tolerance (`None` must equal `None`); strings use `tr_ascii` equality; for lists, each expected item must be `icerir_mi`-matched by some extracted item. Each error is formatted `"<alan>: beklenen X, bulunan Y"`.
  - `eksik_bulma_orani(beklenen: list[str], bulunan: list[str]) -> float | None`
- Produces, in `degerlendir/calistir.py`: `degerlendir(altin_dizini: Path, llm: LLMIstemcisi, ayarlar: Ayarlar) -> dict` and a CLI `python degerlendir/calistir.py [--model-analiz M] [--model-eslestirme M] [--limit-usd 10]`. It inserts the project root into `sys.path`. For each case: `bugun = ihale.yayin_tarihi or date.today()`. Run `on_filtre`; a drop is predicted as GİREMEZ with reason "ön filtre: …". Otherwise run `analiz_al` + `eslestir`. Cost per tender is summed from that ikn's `llm_kullanimi` rows.
- The CLI prints, in this order: per-class accuracy, the confusion matrix, **`Yanlış GİREMEZ: n`** (with the ikns), field errors per case, missing-item recall, and cost per tender (mean, max and total). It writes the full JSON to `degerlendir/sonuclar/{YYYYmmdd-HHMM}-{model_analiz}-{model_eslestirme}.json`.

- [ ] **Step 1: Write the failing tests** in `tests/test_metrikler.py`:
  - `test_matris_ve_dogruluk`: pairs (G,G), (G,Ş), (Ş,Ş), (X,X), (Ş,X) → `matris[G][Ş] == 1`, `sinif_dogrulugu[G] == 0.5`, `yanlis_giremez == 1`
  - `test_alan_hatalari`: expected cost 10 000 000 vs 10 050 000 → no error; vs 12 000 000 → 1 error mentioning `yaklasik_maliyet_tl`; expected belgeler ["Yetkili Satıcı Belgesi"] vs ["yetkili satici belgesi aslı"] → no error
  - `test_degerlendir_sahte_llm`: 2 seed cases with `FakeIstemci` → the result has keys `matris`, `yanlis_giremez`, `maliyet_ihale_basi`, and each case is listed
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement `metrikler.py` and `calistir.py`. Write `altin/README.md` (Turkish) covering the case format, how to label (read the announcement and the idari şartname, decide as an expert for `degerlendir/profil.json`, and write why in `not`), and the required mix: ≥ 3 mal, ≥ 3 hizmet, ≥ 3 yapım, ≥ 4 clear non-fits. Seed 2–3 cases from `ilanlar/`.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass. Commit: `feat: değerlendirme metrikleri ve betiği`
- [ ] **Step 5 (admin, needs a real key and labels):** The admin labels 10–20 cases. Then run both:
  - `python degerlendir/calistir.py --model-analiz claude-sonnet-5-5`
  - `python degerlendir/calistir.py --model-analiz claude-haiku-5-5`
  
  Record in spec §9: the chosen extraction model and why (false GİREMEZ first, then field errors, then cost), and the first accuracy target. Set `EKAP_MODEL_ANALIZ` in `.env` to match.

### Task 15: Deployment, intake form and README

**Files:**
- Create: `dagitim/ekap-ajan.service`, `dagitim/ekap-ajan.timer`, `dagitim/yedekle.sh`, `docs/musteri-profil-formu.md`, `README.md`, `tests/test_profil_formu.py`

**Interfaces:**
- Consumes: `yonet.py calistir`, `FirmaProfili` fields.

- [ ] **Step 1: Write the failing test** `test_formda_tum_alanlar`: read `docs/musteri-profil-formu.md`; every top-level `FirmaProfili.model_fields` name, plus `tipik_ihale_buyuklugu.min_tl`, `tipik_ihale_buyuklugu.max_tl`, `mali.ciro_tl`, `mali.ozkaynak_tl` and `mali.banka_referans_tl`, appears in backticks in the mapping table.
- [ ] **Step 2:** Run `pytest tests/test_profil_formu.py -v`. Expected: FAIL (no file).
- [ ] **Step 3:** Write `docs/musteri-profil-formu.md` (Turkish, ready for Google Forms):
  - About 15 numbered questions in plain language, e.g. "Hangi tür ihalelere giriyorsunuz? (mal / hizmet / yapım)", "Genelde hangi büyüklükte ihalelere teklif veriyorsunuz? En az … TL, en fazla … TL".
  - Experience documents are asked as **güncellenmiş tutar**, year and type.
  - Each question gets an example answer.
  - Then a mapping table: soru no → profil alanı (in backticks) → how to convert. Examples: a comma-separated answer becomes a list; "Tüm Türkiye" becomes `[]`; amounts become TL numbers.
- [ ] **Step 4:** Run `pytest -v`. Expected: all pass.
- [ ] **Step 5:** Write the systemd units:
  - **timer:** `OnCalendar=Mon..Fri *-*-* 07:30:00 Europe/Istanbul`, `Persistent=true`
  - **service:** `Type=oneshot`, `User=ekap`, `WorkingDirectory=/opt/ekap-ajan`, `EnvironmentFile=/opt/ekap-ajan/.env`, `ExecStartPre=/opt/ekap-ajan/dagitim/yedekle.sh`, `ExecStart=/opt/ekap-ajan/.venv/bin/python yonet.py calistir`, `TimeoutStartSec=2h`
  - **yedekle.sh:** `set -euo pipefail`; skip if there is no DB yet; `sqlite3 veri/ekap.db ".backup veri/yedek/ekap-$(date +%F-%H%M).db"`; delete backups older than 14 days
- [ ] **Step 6:** Write `README.md` (Turkish) with these sections:
  1. Ne yapar
  2. Windows kurulumu: `py -3.12 -m venv .venv`, `.\.venv\Scripts\Activate.ps1`, `pip install -r requirements-dev.txt`, `Copy-Item .env.example .env`, `pytest`
  3. Linux/VPS kurulumu: user, `/opt/ekap-ajan`, venv, `.env` with `chmod 600`, `sqlite3` package, copy the units, `systemctl enable --now ekap-ajan.timer`, verify with `systemctl list-timers ekap-ajan.timer`, and copy `veri/yedek` off the server weekly
  4. Gmail uygulama şifresi
  5. Günlük işleyiş: what the admin email means, `journalctl -u ekap-ajan`, `veri/kayitlar/`
  6. Yeni firma ekleme in ≤ 15 min: send the form → fill `firma sablon` output → `profil dogrula` → `firma ekle` → `calistir --firma ID --gonderme` → `rapor-onizle ID`
  7. Maliyet ve limit
  8. Değerlendirme
  9. Gizli anahtar kontrolü before every push: `git log -p --all | Select-String -Pattern "sk-ant-|SMTP_SIFRE=."` (PowerShell) / `git log -p --all | grep -E "sk-ant-|SMTP_SIFRE=."` (bash). Expected output: none.
- [ ] **Step 7:** On the VPS (admin), run `systemd-analyze calendar "Mon..Fri *-*-* 07:30:00 Europe/Istanbul"` (the next run is shown in TRT), then `sudo systemctl start ekap-ajan.service`, then `journalctl -u ekap-ajan -n 50`. Expected: the run summary, and a backup file in `veri/yedek/`.
- [ ] **Step 8:** Run the secret check from README section 9. Expected: no output. Commit: `docs: dağıtım, müşteri profil formu ve README`

---

## Not in this plan
- **Plan 3, the EKAP collector:** `src/toplayici/ekap_kaynagi.py` implementing `Kaynak`, with rate limiting, User-Agent, backoff and recorded HTTP fixtures. It is written after the admin approves the Plan 1 report, and is enabled with `EKAP_KAYNAK=ekap`.
