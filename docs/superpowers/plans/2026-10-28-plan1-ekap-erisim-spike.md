# Plan 1 — EKAP Erişim Spike'ı Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find out whether and how new public EKAP tender announcements can be listed and read politely and reliably, and hand the admin a written recommendation plus 5 saved sample tenders.

**Architecture:** Throwaway investigation. Manual exploration in a browser (network tab) first, then one small script under `spike/` that proves the chosen access path end to end. The outputs that survive are the report and the sample tender files; the script is not production code.

**Tech Stack:** Built-in browser for exploration; Python 3.12 + `httpx` (already pulled in by the `anthropic` SDK in Plan 2; install it alone here) for the proof script.

**Spec:** `docs/superpowers/specs/2026-10-28-ekap-ihale-ajani-design.md` §4.1, §8

## Global Constraints

- Read robots.txt and the site's terms **before** any scripted request; if either forbids automated access to the needed pages, stop and report.
- At most 1 request every 2.5 s; header `User-Agent: ekap-ajan-spike/0.1 (+mailto:<admin email>)`.
- Never automate anything behind login, e-signature or a CAPTCHA. If a CAPTCHA or bot challenge appears, stop and record it. Do not try to get around it.
- Public announcement data only. Do not save contact persons' names or phones into the sample files' structured fields.
- Raw downloaded responses go in `spike/ham/` (gitignored). They are untrusted data, so parse them and never execute them.

## Review Focus

- **Listing pagination and date edges:** a day with more results than one page; tenders published late in the evening. The report must say how "new since date X" is reliably determined.
- **İKN format and uniqueness:** e.g. `2026/1234567`. Confirm one İKN = one tender across re-publications (zeyilname/düzeltme ilanı) and say how corrections appear.
- **Fields that are often absent:** yaklaşık maliyet (usually not public), OKAS codes and province. For each one, the report states how often it is present in the sample.
- **Session tokens / anti-forgery fields:** whether the public JSON endpoints need a cookie or token from a first page load, and how long it lasts.
- **Volume:** tenders per weekday by type, to size LLM cost and choose the first target sector.

---

### Task 1: Rules check (robots.txt and terms)

**Files:**
- Create: `docs/superpowers/spikes/2026-10-28-ekap-erisim-raporu.md` (section "1. Kurallar" only)

- [ ] **Step 1:** Open `https://ekap.kik.gov.tr/robots.txt` and the site's terms of use / KVKK pages in the browser. Copy the relevant lines (Disallow rules, any clauses on automated access) into section 1 with the URL and the date checked.
- [ ] **Step 2:** Decide: allowed / unclear / forbidden for the listing and detail paths. If forbidden, write section 6 "Önerilen yaklaşım" with alternatives (official KİK data services, the Kamu İhale Bülteni, contacting KİK) and **stop the spike here**.

### Task 2: Map the public search flow

**Files:**
- Modify: report section "2. Uç noktalar ve filtreler"

- [ ] **Step 1:** In the browser, open the public tender search (İhale Arama) and run one search for yesterday's announcements. In the network panel, record each request the page makes: URL, method, query/body parameters, response type, and whether it carries cookies or tokens.
- [ ] **Step 2:** Record the available filters and their parameter names: date range, tür (mal/hizmet/yapım/danışmanlık), il, OKAS, ihale usulü. Record page size and how to fetch page 2.
- [ ] **Step 3:** Open 3 detail pages (one each for mal, hizmet and yapım). Record where the full announcement text lives (HTML, embedded JSON or a PDF link) and whether reaching it needs login. Write down the URL pattern that should become `IhaleHam.kaynak_url`.

### Task 3: Proof script and samples

**Files:**
- Create: `spike/ekap_dene.py`, `spike/README.md` (one paragraph: throwaway, how to run)
- Create: `ilanlar/spike-<ikn-tireli>.json` × 5
- Create: `.gitignore` with the line `spike/ham/`

- [ ] **Step 1:** Write `spike/ekap_dene.py` with `httpx`, applying the Global Constraints (2.5 s sleep, User-Agent, 3 retries with exponential backoff on 5xx/timeouts). It lists one day's announcements through the path found in Task 2, saves the raw responses to `spike/ham/`, and prints the count per tür.
- [ ] **Step 2:** Run `python spike/ekap_dene.py --tarih <a recent weekday>`. Expected: a non-zero count per tür and no 4xx responses.
- [ ] **Step 3:** Convert 5 tenders into the `IhaleHam` shape below and save them in `ilanlar/`. Pick one mal, one hizmet, one yapım, one network/IT tender similar to the reference case, and one that clearly does not fit an IT firm. Leave fields that aren't in the source as `null`, and don't guess them.

```json
{"ikn": "2026/1234567", "baslik": "", "idare": "", "il": null, "tur": "mal|hizmet|yapim|null",
 "yayin_tarihi": "YYYY-MM-DD", "son_teklif": "YYYY-MM-DDTHH:MM:00", "yaklasik_maliyet_tl": null,
 "okas_kodlari": [], "metin": "<full announcement text>", "kaynak_url": "", "kaynak": "ekap"}
```

- [ ] **Step 4:** Run the script once more on another weekday and at a different hour. Record response times, error rates and any change in tokens or behaviour.
- [ ] **Step 5: Commit**

```bash
git init   # only if the folder is not a repository yet
git add spike/ekap_dene.py spike/README.md ilanlar/ .gitignore docs/
git commit -m "spike: EKAP erişim denemesi ve örnek ilanlar"
```

### Task 4: Report and stop for approval

**Files:**
- Modify: `docs/superpowers/spikes/2026-10-28-ekap-erisim-raporu.md`

- [ ] **Step 1:** Complete the report sections:
  1. Kurallar
  2. Uç noktalar ve filtreler
  3. `IhaleHam` alan eşlemesi: one table with source field → our field → present in N/5 samples
  4. Hacim: tenders per weekday by tür and by top 10 il, with the 3 largest OKAS groups as candidate target sectors
  5. Güvenilirlik ve riskler: tokens, CAPTCHA, layout-change risk, error rates
  6. Önerilen yaklaşım: one recommendation, with the fallback if it breaks
  7. Plan 3 taslağı: modules, the HTTP fixtures to record for tests, and the parser functions needed
  8. Açık sorular
- [ ] **Step 2:** Commit the report (`git commit -m "docs: EKAP erişim spike raporu"`). Then **stop**: ask the admin to approve section 6 before Plan 3 is written.
