# Plan 3 — EKAP Toplayıcısı Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect newly published public tenders from EKAP every weekday through the JSON API found in the spike, and feed them into the Plan 2 pipeline as `IhaleHam` without any manual step.

**Architecture:** `EkapKaynagi` implements the existing `Kaynak` protocol in two stages. First it lists announcements for the look-back window page by page. Then, using only list fields, it drops tenders that no active firm could want, and fetches the detail (OKAS codes + full announcement text) for the rest straight after each page, because the list `id` is not stable. All HTTP goes through a small `Tasiyici` interface: the real one (`HttpTasiyici`) enforces pacing, User-Agent, TLS settings and retries; tests inject a fake one that serves recorded responses. On a hard failure the collector raises `KaynakHatasi` carrying what it already collected, so the day still runs on partial data.

**Tech Stack:** Python 3.12 stdlib only (`urllib.request`, `ssl`, `json`, `html.parser`) on top of Plan 2. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-28-ekap-ihale-ajani-design.md` §4.1 and §9 (decision 9). Source of every API fact: `docs/superpowers/spikes/2026-10-28-ekap-erisim-raporu.md`. Builds on `docs/superpowers/plans/2026-10-28-plan2-cekirdek-hat.md` (implemented).

## Global Constraints

- Everything in Plan 2's Global Constraints still applies: Turkish identifiers, Windows + Linux, no new runtime dependencies, secrets only in `.env`.
- Base URL `https://ekapv2.kik.gov.tr/b_ihalearama/api`. All calls are `POST` with a JSON body and the headers `Content-Type: application/json` and `Accept: application/json`.
- At least `ayarlar.istek_araligi_sn` (default 2.5 s) between any two requests, including retries.
- User-Agent `ekap-ajan/0.1 (+mailto:<EKAP_ILETISIM_EPOSTA>)`, or `ekap-ajan/0.1` when that setting is empty. The admin's address is never used by default.
- TLS context: `ssl.create_default_context()` + `set_ciphers("DEFAULT:@SECLEVEL=1")`. Certificate verification stays on, and the context is used only for this host.
- Retries: at most 3 attempts with 2 s / 4 s backoff, only for 5xx, timeouts and connection errors. A 4xx (403, 429 …) or a non-JSON body means bot protection or an API change. It stops the collector at once with `KaynakHatasi` and is never retried or worked around.
- Page size 50 (the server's maximum). Only `ihaleDurum == "2"` (katılıma açık) is collected.
- The list `id` is never stored, and it is used only within the same page iteration it came from. İKN is the only key.
- No network access in unit tests. Recorded fixtures live under `tests/fikstur/ekap/`.
- Out of scope (spike §8 decision): correction notices (zeyilname), document downloads, anything behind login.

## Review Focus

1. **Turkish upper-case province names from the API** ("İZMİR", "ŞANLIURFA", "ISPARTA"): `il` must come out as "İzmir", "Şanlıurfa", "Isparta". Python's `.title()` turns "İZMİR" into "İzmi̇r". Pinned in Task 1 (`test_tr_baslik`) and Task 2 (`test_il_turkce_baslik`).
2. **Pagination drift:** if a tender is published while the list is being paged, items shift and one İKN can appear on two pages (or one can be missed). It must be yielded once, and the 3-day look-back picks up a missed one the next morning. Pinned in Task 4 (`test_ayni_ikn_iki_sayfada_bir_kez`).
3. **Bot protection appearing mid-run** (403 / 429 / an HTML page instead of JSON): the collector stops at once without retrying, keeps what it already has, and the run continues on that partial set with an admin warning. Pinned in Task 3 (`test_4xx_tekrar_denenmez`, `test_json_olmayan_yanit`) and Task 4 (`test_yarida_kesilirse_kismi_sonuc`).
4. **Detail responses with missing parts** (`ilanList` empty, `ihtiyacKalemiOkasList` null, `ihaleTarihSaat` null): the result is a valid `IhaleHam` with `None` / `[]` / `""`, never a crash. Pinned in Task 2 (`test_eksik_detay_alanlari`).
5. **One detail call failing** (expired `id`, 5xx after retries): only that tender is skipped. It is not saved, so it is collected again on the next run. Pinned in Task 4 (`test_detay_hatasi_tek_ihaleyi_atlar`).

## File Structure

```
src/toplayici/ekap_kaynagi.py     ListeOzeti, parsing helpers, Tasiyici, HttpTasiyici, EkapKaynagi, liste_secici
src/toplayici/kaynak.py           (modify) KaynakHatasi carries partial results
src/metin.py                      (modify) tr_baslik
src/on_filtre.py                  (modify) faaliyet_kontrolu flag
src/ayarlar.py                    (modify) iletisim_eposta
src/calisma.py                    (modify) _topla keeps partial results
yonet.py                          (modify) EKAP_KAYNAK=ekap wiring, `topla` command
tests/fikstur/ekap/*.json         trimmed recorded responses
tests/fikstur/ekap_fikstur_yap.py one-off script that builds the fixtures from spike/ham/
tests/test_ekap_ayristirma.py, tests/test_ekap_tasiyici.py, tests/test_ekap_kaynagi.py
README.md, .env.example           (modify) how to switch to EKAP
```

---

### Task 1: Groundwork in Plan 2 code

**Files:**
- Modify: `src/metin.py`, `src/on_filtre.py`, `src/toplayici/kaynak.py`, `src/ayarlar.py`, `src/calisma.py`, `.env.example`
- Test: `tests/test_metin.py`, `tests/test_on_filtre.py`, `tests/test_ayarlar.py`, `tests/test_calisma.py`

**Interfaces:**
- Produces:
  - `metin.tr_baslik(s: str) -> str`: each whitespace-separated word becomes its first character unchanged + `tr_kucuk(rest)`. Hyphenated parts are handled the same way ("AFYON-KARAHİSAR" → "Afyon-Karahisar").
  - `on_filtre(ihale, profil, bugun, ayarlar, faaliyet_kontrolu: bool = True) -> OnFiltreSonucu`: with `False`, rule 3 (faaliyet) is skipped. Used for list-level pre-selection, where there is no text or OKAS yet.
  - `KaynakHatasi(mesaj: str, kismi: list[IhaleHam] | None = None)`, with attribute `.kismi: list[IhaleHam]` (default `[]`).
  - `Ayarlar.iletisim_eposta: str = ""` (env `EKAP_ILETISIM_EPOSTA`).
  - `calisma._topla`: on `KaynakHatasi`, it saves `hata.kismi` (counted in `getirilen` / `yeni`) and still records `f"kaynak {k.ad}: {hata}"`.

- [ ] **Step 1: Write the failing tests:**
  - `test_tr_baslik`: `"İZMİR"` → `"İzmir"`; `"ŞANLIURFA"` → `"Şanlıurfa"`; `"ISPARTA"` → `"Isparta"`; `"AFYON-KARAHİSAR"` → `"Afyon-Karahisar"`; `"KIRIKKALE"` → `"Kırıkkale"`
  - `test_faaliyet_kontrolu_kapali`: an ihale with `metin=""` and a profile with keywords → `on_filtre(..., faaliyet_kontrolu=False).gecti is True`; with the default flag it is `False`
  - `test_iletisim_eposta`: `ayarlari_yukle({"EKAP_ILETISIM_EPOSTA": "a@b.com"}).iletisim_eposta == "a@b.com"`; the default is `""`
  - `test_kaynak_kismi_sonuc_kaydedilir` (test_calisma): `FakeKaynak` raises `KaynakHatasi("403", kismi=[ornek_ihale("2026/1")])` → `sonuc.yeni == 1`, the email is sent, and hatalar contains `"kaynak"`
- [ ] **Step 2:** Run `pytest -q`. Expected: 4 new failures (missing name / attribute / argument).
- [ ] **Step 3:** Implement the five modifications. Add `EKAP_ILETISIM_EPOSTA=` to `.env.example`.
- [ ] **Step 4:** Run `pytest -q`. Expected: all pass (121 existing + 4 new).
- [ ] **Step 5: Commit** (if Git is installed): `git commit -am "feat: toplayıcı için hazırlık (tr_baslik, kısmi kaynak sonucu)"`

### Task 2: Recorded fixtures and parsing

**Files:**
- Create: `tests/fikstur/ekap_fikstur_yap.py`, `tests/fikstur/ekap/liste-1.json`, `liste-2.json`, `detay-2026-1874068.json`, `detay-2026-2082996.json`
- Create: `src/toplayici/ekap_kaynagi.py` (parsing part), `tests/test_ekap_ayristirma.py`

**Interfaces:**
- Consumes: `IhaleHam`, `metin.tr_baslik`.
- Produces, in `src/toplayici/ekap_kaynagi.py`:
  - `TABAN = "https://ekapv2.kik.gov.tr/b_ihalearama/api"`; `TUR = {"1": "mal", "2": "yapim", "3": "hizmet"}` (anything else → `None`)
  - `@dataclass(frozen=True) class ListeOzeti`: `id: str`, `ikn: str`, `baslik: str`, `idare: str`, `il: str | None`, `tur: str | None`, `durum: str`, `son_teklif: datetime | None`
  - `liste_ozeti(ham: dict) -> ListeOzeti`: maps `ihaleAdi`, `idareAdi`, `ihaleIlAdi` (→ `tr_baslik`, empty → `None`), `ihaleTip` (str key → `TUR`), `ihaleDurum`, and `ihaleTarihSaat` (`%d.%m.%Y %H:%M`, missing/unparsable → `None`). A missing `ikn` or `id` raises `KaynakHatasi("beklenmeyen liste öğesi")`.
  - `html_metin(html: str) -> str`: the spike's `_MetinCikar` logic. Block tags (`br p div tr table center li h1 h2 h3`) become newlines and `td` becomes a space. Whitespace is collapsed per line and empty lines are dropped.
  - `kalici_baglanti(ikn: str) -> str`: `"https://ekapv2.kik.gov.tr/ekap/search/" + ikn.replace("/", "_")`
  - `ihale_ham_olustur(ozet: ListeOzeti, detay: dict) -> IhaleHam`:
    - `yayin_tarihi` = `ilanList[0].ilanTarihi[:10]`, or `None` if absent
    - `okas_kodlari` = `[o["kodu"] for o in ihtiyacKalemiOkasList or []]`
    - `metin` = the `html_metin` of each `ilanList[].veriHtml`, joined with `"\n\n"`
    - `kaynak_url` = `kalici_baglanti`
    - `kaynak = "ekap"`
    - `yaklasik_maliyet_tl = None`
    - A missing `detay["item"]` raises `KaynakHatasi("beklenmeyen detay yanıtı")`.
- `ekap_fikstur_yap.py` (run once, by hand, then committed with its output): reads `spike/ham/liste-2026-10-27-00000.json` and `-00050.json`, keeps the first 3 items of each, sets `ihaleDurum` to `"2"` on all of them (so the counts in the tests below are deterministic), sets the first item's `ikn`/`id` to the BT tender `2026/1874068` and a matching id, and writes them as `liste-1.json` / `liste-2.json` with `totalCount: 6`. The second page's first item is replaced by a copy of the first page's last item (the drift case). It also copies two detail files, trimming `veriHtml` to its first 3000 characters.

- [ ] **Step 1:** Write and run `python tests/fikstur/ekap_fikstur_yap.py`. Expected: 4 files in `tests/fikstur/ekap/`, each under 40 KB.
- [ ] **Step 2: Write the failing tests** in `tests/test_ekap_ayristirma.py`:
  - `test_liste_ozeti`: the first item of `liste-1.json` → `ikn` matches `^\d{4}/\d+$`; `durum == "2"`; `son_teklif` is a `datetime`
  - `test_il_turkce_baslik`: `liste_ozeti({**oge, "ihaleIlAdi": "İZMİR"}).il == "İzmir"`; `""` → `None`
  - `test_tur_eslemesi`: `ihaleTip` `"1"` / `"2"` / `"3"` / `"4"` → `"mal"` / `"yapim"` / `"hizmet"` / `None`
  - `test_liste_ozeti_eksik_ikn`: the item without `ikn` → `KaynakHatasi`
  - `test_ihale_ham_olustur_bt_ihalesi`: `detay-2026-1874068.json` → `okas_kodlari == ["72260000", "72263000", "48820000", "30230000"]`, `yayin_tarihi == date(2026, 10, 27)`, `"4.3.1" in metin`, `"<" not in metin`, `kaynak_url.endswith("/ekap/search/2026_1874068")`
  - `test_eksik_detay_alanlari`: `{"item": {"ilanList": None, "ihtiyacKalemiOkasList": None}}` → `yayin_tarihi is None`, `okas_kodlari == []`, `metin == ""`
  - `test_beklenmeyen_detay`: `{}` → `KaynakHatasi`
  - `test_html_metin`: `"<b>A</b><br/>B<table><tr><td>x</td><td>y</td></tr></table>"` → `"A\nB\nx y"`
- [ ] **Step 3:** Run `pytest tests/test_ekap_ayristirma.py -v`. Expected: FAIL (import error).
- [ ] **Step 4:** Implement the parsing part of `ekap_kaynagi.py`.
- [ ] **Step 5:** Run `pytest -q`. Expected: all pass.
- [ ] **Step 6: Commit**: `feat: EKAP yanıt ayrıştırma ve kayıtlı fikstürler`

### Task 3: HTTP transport

**Files:**
- Modify: `src/toplayici/ekap_kaynagi.py`
- Create: `tests/test_ekap_tasiyici.py`

**Interfaces:**
- Consumes: `Ayarlar` (`istek_araligi_sn`, `iletisim_eposta`), `KaynakHatasi`.
- Produces:
  - `class Tasiyici(Protocol)`: `def post(self, yol: str, govde: dict) -> dict: ...` (`yol` such as `"/Ihale/GetListByParameters"`)
  - `class HttpTasiyici`: `__init__(self, ayarlar: Ayarlar, acici=urllib.request.urlopen, uyku=time.sleep, saat=time.monotonic)`. Attributes `user_agent: str` and `istek_sayisi: int`. `post` builds the request with the Global Constraints headers and `context=` the SECLEVEL=1 TLS context, with a 30 s timeout. It sleeps so that at least `istek_araligi_sn` passes between request starts. The error policy:

| Condition | Behaviour |
|---|---|
| `HTTPError` with code ≥ 500, `URLError`, `TimeoutError` | Retry up to 3 attempts in total; sleep 2 s then 4 s before attempts 2 and 3 (on top of the pacing). After the 3rd failure, `KaynakHatasi(f"{yol}: 3 deneme başarısız: {son hata}")`. |
| `HTTPError` with code < 500 | `KaynakHatasi(f"{yol}: HTTP {kod} (bot koruması veya API değişikliği olabilir)")` at once, no retry. |
| Body is not valid JSON, or not a `dict` | `KaynakHatasi(f"{yol}: JSON olmayan yanıt")`. No retry. |

- [ ] **Step 1: Write the failing tests** with a fake `acici` that records requests and returns objects with `.read()` and the context-manager protocol, plus a fake clock and a recording `uyku`:
  - `test_basliklar_ve_govde`: the request method is POST; the URL is `TABAN + yol`; `Content-Type` is `application/json`; the body decodes to the given dict; `context` was passed and its `verify_mode == ssl.CERT_REQUIRED`
  - `test_user_agent`: `iletisim_eposta="a@b.com"` → `"ekap-ajan/0.1 (+mailto:a@b.com)"`; empty → `"ekap-ajan/0.1"`
  - `test_istek_araligi`: two `post` calls with the clock not advancing → `uyku` called with ≈ 2.5 before the 2nd request
  - `test_5xx_tekrar_dener`: 500, 500, then OK → returns the dict; 3 requests; the backoff sleeps 2 and 4 are among the `uyku` calls
  - `test_5xx_uc_kez_sonra_hata`: 503 × 3 → `KaynakHatasi` whose message contains `"3 deneme"`
  - `test_4xx_tekrar_denenmez`: 429 → `KaynakHatasi` containing `"HTTP 429"`; exactly 1 request
  - `test_json_olmayan_yanit`: body `b"<html>dogrulama</html>"` → `KaynakHatasi` containing `"JSON olmayan"`; 1 request
- [ ] **Step 2:** Run `pytest tests/test_ekap_tasiyici.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `Tasiyici` and `HttpTasiyici`.
- [ ] **Step 4:** Run `pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: EKAP HTTP taşıyıcı (hız sınırı, TLS, yeniden deneme)`

### Task 4: `EkapKaynagi`

**Files:**
- Modify: `src/toplayici/ekap_kaynagi.py`
- Create: `tests/test_ekap_kaynagi.py`

**Interfaces:**
- Consumes: `Tasiyici`, the parsing functions from Task 2, `on_filtre(..., faaliyet_kontrolu=False)`, `Firma`, `Ayarlar`.
- Produces:
  - `class EkapKaynagi`:
    - `ad = "ekap"`
    - `__init__(self, tasiyici: Tasiyici, on_secici: Callable[[ListeOzeti], bool] = lambda o: True, bilinen: Callable[[str], bool] = lambda ikn: False, bugun: Callable[[], date] = date.today)`
    - `yeni_ihaleleri_getir(self, since: date) -> list[IhaleHam]`
    - Counters set by each call, for logging: `self.son_istatistik: dict[str, int]` with keys `listelenen`, `acik`, `bilinen`, `secilmeyen`, `detay`, `detay_hatasi`
  - `liste_secici(firmalar: list[Firma], ayarlar: Ayarlar, bugun: date) -> Callable[[ListeOzeti], bool]`: True if **any** firm passes `on_filtre` on a text-less `IhaleHam` built from the list fields, with `faaliyet_kontrolu=False`. With no active firms it always returns False.

`yeni_ihaleleri_getir` algorithm:
1. Body: `{"ilanTarihSaatBaslangic": f"{since}T00:00:00", "ilanTarihSaatBitis": f"{bugun()}T23:59:59", "paginationTake": 50, "paginationSkip": skip}`. Start with `skip = 0`.
2. Per page:
   - `yanit = tasiyici.post("/Ihale/GetListByParameters", govde)`.
   - If `yanit` lacks a `list` or an integer `totalCount`, raise `KaynakHatasi("beklenmeyen liste yanıtı", kismi=toplanan)`.
3. For each item, in order:
   - Skip if `durum != "2"`, if its İKN was already seen in this call, if `bilinen(ikn)`, or if `not on_secici(ozet)`.
   - Otherwise `detay = tasiyici.post("/IhaleDetay/GetByIhaleIdIhaleDetay", {"ihaleId": ozet.id})` and append `ihale_ham_olustur(ozet, detay)`.
   - If that detail call raises `KaynakHatasi` whose message starts with `"/IhaleDetay"` and contains `"3 deneme"`, increment `detay_hatasi`, log a warning and continue.
   - Any other `KaynakHatasi` (4xx, non-JSON) re-raises with `kismi=toplanan`.
4. Stop when `skip + 50 >= totalCount` or the page is empty; otherwise `skip += 50`.
5. Log `"EKAP: %(listelenen)d listelendi, %(detay)d detay çekildi …"` from `son_istatistik` and return the collected list.

- [ ] **Step 1: Write the failing tests** with `FakeTasiyici(yanitlar: dict[str, list | Callable])`, which serves `liste-1.json` / `liste-2.json` by `paginationSkip` and detail fixtures by `ihaleId` (detail for unknown ids → a minimal `{"item": {"ilanList": [], "ihtiyacKalemiOkasList": []}}`):
  - `test_iki_sayfa_toplanir`: 6 list items with 1 duplicate → 5 `IhaleHam`; list requests with `paginationSkip` 0 and 50; body dates `since` and `bugun()`
  - `test_ayni_ikn_iki_sayfada_bir_kez`: the duplicated İKN appears once in the result
  - `test_yalnizca_katilima_acik`: an item with `ihaleDurum "6"` is not detailed and not returned
  - `test_bilinen_ihale_detaylanmaz`: `bilinen` returns True for one İKN → no detail request with its id
  - `test_on_secici_eler`: `on_secici=lambda o: o.tur == "hizmet"` → only hizmet tenders are detailed
  - `test_detay_hatasi_tek_ihaleyi_atlar`: the detail for one id raises `KaynakHatasi("/IhaleDetay/GetByIhaleIdIhaleDetay: 3 deneme başarısız: …")` → the others are returned, `son_istatistik["detay_hatasi"] == 1`
  - `test_yarida_kesilirse_kismi_sonuc`: page 2 raises `KaynakHatasi("…HTTP 403…")` → `KaynakHatasi` raised with `len(hata.kismi) == 3` (page 1's open tenders)
  - `test_beklenmeyen_liste`: `{"foo": 1}` → `KaynakHatasi` containing `"beklenmeyen liste"`
  - `test_liste_secici`: a firm with types `["mal"]` and provinces `["Ankara"]`: a mal tender in Ankara → True; hizmet → False; il `None` → True; no firms → False; a deadline 1 day away → False
- [ ] **Step 2:** Run `pytest tests/test_ekap_kaynagi.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `EkapKaynagi` and `liste_secici`.
- [ ] **Step 4:** Run `pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit**: `feat: EkapKaynagi (iki aşamalı toplama)`

### Task 5: Wiring, `topla` command, live check, docs

**Files:**
- Modify: `yonet.py`, `tests/test_yonet.py`, `README.md`, `.env.example`

**Interfaces:**
- Consumes: `EkapKaynagi`, `HttpTasiyici`, `liste_secici`, `Depo`.
- Produces:
  - `yonet._kaynaklar(ayarlar: Ayarlar, depo: Depo, tarih: date) -> list[Kaynak]`. `"dosya"` → `[DosyaKaynagi(Path("ilanlar"))]`. `"ekap"` → `[EkapKaynagi(HttpTasiyici(ayarlar), on_secici=liste_secici(depo.firmalar(), ayarlar, tarih), bilinen=lambda ikn: depo.ihale_getir(ikn) is not None, bugun=lambda: tarih)]`. Anything else → `ValueError`.
  - New command `topla [--tarih] [--gun N] [--hepsi] [--dizin D]`:
    - Collects without any LLM call. `--gun` defaults to 1. `--hepsi` disables the firm pre-selection (`on_secici` always True) and is useful for building the golden set.
    - Saves the tenders to the store.
    - With `--dizin`, also writes each tender as `D/<ikn-with-/-replaced-by-->.json` (the `IhaleHam` shape that `DosyaKaynagi` and the golden set use).
    - Prints `f"{n} ihale toplandı ({yeni} yeni)"` and the counters. A `KaynakHatasi` prints the error and returns 1 after saving the partial results.
  - `ana()` gains a `tasiyici=` keyword parameter (tests only); when set, `_kaynaklar` uses it instead of `HttpTasiyici`.

- [ ] **Step 1: Write the failing tests** in `tests/test_yonet.py`:
  - `test_kaynak_ekap_secilir`: `_kaynaklar(replace(ayar, kaynak="ekap"), depo, d)[0].ad == "ekap"`; `"x"` → `ValueError`
  - `test_topla_dizine_yazar`: `ana(["topla", "--hepsi", "--dizin", str(tmp_path), "--tarih", "2026-10-27"], depo=depo, ayarlar=replace(ayar, kaynak="ekap"), tasiyici=FakeTasiyici(...))` → exit 0; 5 `*.json` files in `tmp_path`, each loading as `IhaleHam`; `depo.ihale_getir(<one İKN>)` is not `None`
  - `test_topla_hata_kismi_kaydeder`: page 2 → 403 → exit 1; page 1's tenders are in the store
- [ ] **Step 2:** Run `pytest tests/test_yonet.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement the wiring and `topla`. Move `FakeTasiyici` to `tests/sahte.py` so both test files share it.
- [ ] **Step 4:** Run `pytest -q`. Expected: all pass.
- [ ] **Step 5 (live check, real network, no LLM):** `python yonet.py topla --hepsi --gun 1 --dizin cikti/ekap-deneme`, with `EKAP_KAYNAK=ekap` in `.env`. Expected: about 600–700 tenders on a weekday (spike §4), about 15 list requests + one detail request per open tender (~30 min, so run it in the background), 0 HTTP errors, and files in `cikti/ekap-deneme/` that open as `IhaleHam`. Spot-check one file against its EKAP link. Then run `python yonet.py topla --gun 1` without `--hepsi`, with the sample firm active. Expected: far fewer detail requests (only the firm's types and provinces).
- [ ] **Step 6:** Update `README.md`: a new section "EKAP kaynağına geçiş" covering `EKAP_KAYNAK=ekap`, `EKAP_ILETISIM_EPOSTA`, the `topla` command (including `--hepsi --dizin` for collecting golden set candidates), what a `kaynak ekap: HTTP 403` warning means ("site bot koruması açmış olabilir; toplayıcı durdu, aşmaya çalışmaz — spike raporu §5"), and the expected daily collection time (5–15 min). Add `EKAP_KAYNAK=ekap` as a commented alternative in `.env.example`.
- [ ] **Step 7: Commit**: `feat: EKAP kaynağını devreye al, topla komutu`

---

## Not in this plan
- Correction notices (zeyilname): re-fetching the details of still-open tenders. To be decided after the pilot (spike §8, question 2).
- A headless-browser fallback: only if plain HTTP is ever blocked (spike §6).
