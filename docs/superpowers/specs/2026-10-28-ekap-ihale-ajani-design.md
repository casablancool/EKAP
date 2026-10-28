# EKAP İhale Ajanı — Product & Build Spec

> Status: reviewed 2026-10-28. Section 2 was rewritten because no prototype code exists; section 9 records the decisions taken in review.

---

## 1. Goal

Turn the EKAP idea into a **paid subscription service** for Turkish firms that bid on public tenders.

Every weekday the system:
1. collects newly published tenders from EKAP,
2. extracts each tender's requirements **once**,
3. checks them against **each customer firm's profile**,
4. emails each firm a short digest: which tenders they can bid on, which they could bid on if they fix something, and why.

**Business context (affects priorities):**
- Run by one person (the admin) about 15 hours a week, alongside a job search.
- It must keep running unattended: no daily manual work except onboarding new customers and answering emails.
- First customers come from direct sales and content, so the first 5–10 customers are onboarded **manually by the admin**. No self-service sign-up yet.
- Success at 3 months: 5 pilot firms receiving digests, at least 1 paying, LLM cost per firm per month known and low.

---

## 2. Starting point

**No code exists yet.** The project starts from an empty folder. The prototype pieces the original spec assumed must be built as part of the core plan:

| File | Role |
|---|---|
| `src/analiz.py` | LLM extraction: tender text → structured JSON (requirements, deadlines, financial criteria, required documents) |
| `src/eslestir.py` | Rule-based pre-checks plus LLM matching of tender JSON vs. a firm profile → **GİREBİLİR / ŞARTLI GİREBİLİR / GİREMEZ** with reasons |
| `src/yardimci.py` | Shared LLM call helper: Claude call, safe structured parsing, raw output saved to `cikti/_hata_*.txt` on failure; models from env vars |
| `calistir.py` | Single-tender debug runner: `python calistir.py ilanlar/x.json` writes `.json` plus a readable `.txt` to `cikti/` |
| `profil.json` | Sample firm profile |
| `ilanlar/` | Sample tender files |

Lessons to carry over from the idea phase:
- The report must be **short** for end users.
- The profile needs a **typical tender size** field (min/max budget the firm realistically bids on).
- Reference case: a network infrastructure tender (Ankara Metropolitan Municipality type) where the firm lacks a *Yetkili Satıcı Belgesi* and the experience ratio must be computed correctly.

Conventions: Turkish names for modules, functions and user-facing text; code comments may be Turkish. Customer-facing output is **Turkish only**.

---

## 3. Scope

### In scope (MVP)
1. Automatic daily tender collection from EKAP (public announcements only).
2. Tender store with de-duplication.
3. Cheap pre-filter before any LLM call.
4. One extraction per tender, cached and reused for all customers.
5. Matching against multiple firm profiles.
6. Short Turkish email digest per firm.
7. Scheduled unattended run.
8. Evaluation set and script to measure accuracy.
9. Simple admin CLI to add, edit and pause customers.

### Out of scope (do NOT build now)
- Web dashboard or customer login
- Self-service sign-up, online payment, or invoicing integration (invoicing is manual)
- Downloading documents behind e-signature or login, or submitting bids
- Preparing bid documents for the customer
- WhatsApp or Telegram delivery
- Non-EKAP sources (EU TED, municipalities' own sites); design so a second source *can* be added later, but don't build it
- Multi-user admin, roles, permissions

---

## 4. Architecture

```
[1 Toplayıcı]  →  [2 Depo (SQLite)]  →  [3 Ön filtre]  →  [4 Analiz (cache)]  →  [5 Eşleştirme]  →  [6 Rapor + E-posta]
  EKAP fetch        tenders, firms,       per firm:           LLM extraction,       rules + LLM,         digest per firm
                    analyses, matches,    cheap rules,        once per tender       per (tender, firm)
                    sent log              no LLM
                                    ↑
                          [7 Yönetim CLI]  (firms, profiles, manual runs)
                          [8 Değerlendirme] (golden set, accuracy report)
                          [9 Zamanlayıcı]   (daily scheduled run)
```

### 4.1 Toplayıcı (collector) — `src/toplayici/`
- **Step 0 is a spike (throwaway):** investigate how new tender announcements can be listed and read from the public EKAP site (ekap.kik.gov.tr): listing pages, filters (date, tender type mal/hizmet/yapım, province, OKAS codes), detail pages, any public JSON endpoints the site itself uses. Report findings and a recommended approach **before** building the real collector.
- Rules (non-negotiable): read robots.txt and terms; low request rate (1 request every 2–3 s, configurable); self-identifying User-Agent; retry with backoff; never automate anything behind login or e-signature.
- Interface: `yeni_ihaleleri_getir(since: date) -> list[IhaleHam]`, where `IhaleHam` has `ikn`, title, authority, province, type, dates, OKAS/CPV codes if available, full announcement text, source URL.
- The source sits behind a small `Kaynak` protocol so another source could be added later.
- If fetching fails, the run continues with what it has and logs the error.

### 4.2 Depo (storage) — `src/depo.py`
- **SQLite** (single file, `veri/ekap.db`), simple migrations.
- Tables: `ihaleler`, `analizler`, `firmalar`, `eslesmeler`, `gonderimler` (refined in the plan).
- De-dupe on `ikn`. Re-runs on the same day are **idempotent**: no double analysis, no double emails.
- Contact persons' names and phones in tenders are personal data (KVKK). Store only what's needed; never put them in emails.

### 4.3 Ön filtre (pre-filter, no LLM) — `src/on_filtre.py`
For each (tender, active firm), cheaply discard obvious non-matches: tender type not in the firm's types; province not in the firm's service area (if set); OKAS/CPV or keyword mismatch; deadline passed or too close (configurable, default under 3 days); estimated cost (if published) outside the firm's typical tender size range.
**Recall-first:** when unsure, let the tender through. Log why each tender was dropped.

### 4.4 Analiz (extraction, cached) — `src/analiz.py`
- Extraction runs **once per tender** that passes at least one firm's pre-filter, stored in `analizler`.
- Versioned prompt (`prompt_version`). Old cached results stay valid unless the admin explicitly re-runs.
- Haiku if the eval shows acceptable accuracy, otherwise Sonnet. Model set via env/config.

### 4.5 Eşleştirme (matching) — `src/eslestir.py`
- Input: extraction JSON plus firm profile. Output: `GİREBİLİR / ŞARTLI GİREBİLİR / GİREMEZ`, a short list of reasons, and for ŞARTLI a list of **what is missing**.
- Deterministic rules first (experience ratio, turnover and equity ratios, mandatory certificates). LLM only for what rules can't judge. Decisions explainable. Every result stored.

### 4.6 Rapor + E-posta — `src/rapor.py`, `src/eposta.py`
- One email per firm per run, **only if** there is at least one GİREBİLİR or ŞARTLI tender. Optional weekly "bu hafta uygun ihale çıkmadı" note (default off).
- Per tender about 5 lines: title, authority, province; decision (✅ GİREBİLİR / ⚠️ ŞARTLI); estimated cost if public, bid deadline; 1–3 bullet reasons, and for ŞARTLI "Eksik: …"; link to the EKAP announcement.
- Sorted GİREBİLİR before ŞARTLI, then by deadline (soonest first).
- GİREMEZ tenders only counted ("12 ihale daha incelendi, uygun değil").
- HTML email with plain-text fallback; SMTP settings from `.env` (Gmail app password works).
- Footer disclaimer: decision support only, the firm must verify official documents.
- Every send logged in `gonderimler`.

### 4.7 Yönetim CLI — `yonet.py`
- `firma ekle` (from a JSON file), `firma listele`, `firma duzenle <id>`, `firma durdur/aktif <id>`
- `profil dogrula <dosya>`
- `calistir [--tarih] [--firma <id>] [--gonderme]` (`--gonderme` = dry run, digest written to a file)
- `rapor-onizle <firma_id>`

**Firm profile schema:** name, contact emails; tender types (mal / hizmet / yapım); keywords and OKAS/CPV codes; service provinces (empty = all Türkiye); **typical tender size min/max TL**; certificates held; experience documents (amount, year, type); financials (turnover, equity, bank reference capacity — optional); notes.

A Turkish **profile intake template** for new customers, plus the mapping from answers to `profil.json`.

### 4.8 Değerlendirme (evaluation) — `degerlendir/`
- Golden set: 10–20 real EKAP tenders across mal, hizmet and yapım, including clear non-fits; each hand-labeled with expected decision and key missing items.
- `python degerlendir/calistir.py` prints accuracy per class, confusion matrix, **false GİREMEZ count** (priority metric), extraction field errors, token cost per tender.
- Run before any prompt or model change.

### 4.9 Zamanlayıcı (scheduling)
- Weekday run at 07:30 Türkiye time. The DB must survive between runs.
- On failure, email the admin. Never send customers a broken digest.

---

## 5. Cross-cutting requirements
- **Secrets:** API key and SMTP credentials only in `.env` / server environment; `.env`, `veri/`, `cikti/` in `.gitignore`; keys never logged; history checked for keys before the first push.
- **Cost control:** input/output tokens logged per call; per-run and per-firm cost summary; configurable daily LLM spend cap — above it, stop analysing and alert the admin.
- **Logging:** readable log per run (fetched / filtered / analysed / matched / emailed counts, errors).
- **Robustness:** one tender's failure never stops the run; logged, skipped, `_hata_*.txt` kept.
- **Testing:** pytest for pre-filter, numeric rules, profile validation, idempotency, digest rendering; LLM mocked; real calls only in the eval script.
- **Platform:** Windows/PowerShell locally and Linux on the server/CI; README covers both.
- **Dependencies:** minimal, pinned in `requirements.txt`.

---

## 6. Build order
1. Spike (Plan 1) → report → approval.
2. Core pipeline on a local file source (Plan 2).
3. EKAP collector from the approved spike approach (Plan 3, written after the spike).

## 7. Definition of done (MVP)
- [ ] A scheduled weekday run fetches new EKAP tenders without manual action.
- [ ] A firm can be onboarded in under 15 minutes with the intake template and `yonet.py`.
- [ ] Each active firm gets at most one short Turkish digest per day, only when there's something relevant.
- [ ] Re-running the same day sends no duplicates.
- [ ] The eval script reports accuracy, false GİREMEZ count and cost per tender.
- [ ] Cost per firm per month is printed in the run summary.
- [ ] The admin is emailed if a run fails.
- [ ] No secrets in the repo; README explains Windows and server setup.

## 8. Open questions (still open)
- EKAP access method and reliability — answered by the spike.
- Haiku vs. Sonnet for extraction — answered by the eval.
- Whether the first target sector needs extra profile fields — answered by spike volume data.

## 9. Decisions taken in review (2026-10-28)
1. **Three plans:** Plan 1 spike, Plan 2 core on a local `DosyaKaynagi`, Plan 3 EKAP collector.
2. **Scheduling on a small VPS** with a systemd timer and a backup before each run. Not GitHub Actions, because the DB holds customer data (KVKK) and Actions offers no durable, private storage between runs and its cron often runs late. GitHub Actions is still used for CI tests (Windows + Linux).
3. **"No duplicates"** = at most one successful digest per firm per date; a failed send is retried on the next run that day; a tender is never listed twice to the same firm.
4. **Daily cap in USD**, computed from tokens and a price table in config (default 5 USD/day).
5. **Rule-based hard rejection skips the LLM:** only when the firm's largest experience document is below 25 % (configurable) of the required amount. Every other rule shortfall becomes ŞARTLI, never GİREMEZ.
6. **Models:** extraction default `claude-sonnet-5-5` (switch to `claude-haiku-5-5` if the eval allows); matching default `claude-opus-5-5`; both via env. Matching sends the extraction JSON, not the full tender text, to keep cost per firm low.
7. **Firm onboarding via JSON file** (from the intake template), not an interactive prompt.
8. **Maximum-bid rule** (after the spike, approved 28.10.2026). EKAP gives experience, turnover and bank-reference thresholds as a share of the firm's own bid, and yaklaşık maliyet is almost never published. The rules therefore compute the highest bid the firm can make and compare it with yaklaşık maliyet (when published) or the firm's typical minimum tender size. Only a shortfall against a published yaklaşık maliyet can produce a rule-based GİREMEZ. The digest shows the limit as a reason line ("… en fazla X TL teklif verebilirsiniz").
9. **EKAP access** through the public JSON API of ekapv2.kik.gov.tr (spike report `docs/superpowers/spikes/2026-10-28-ekap-erisim-raporu.md`), approved 28.10.2026.
