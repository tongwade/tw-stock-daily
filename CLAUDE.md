# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A daily stock-information website for Taiwan equities. The data is **self-generated locally** by Python scripts (a market-signals engine + two per-stock 分點 crawlers), turned into Excel/CSV, then `build.py` converts those into a compact static site under `site/`, published to **GitHub Pages via a GitHub Actions workflow** (push to `main` auto-deploys). The **served site** has no backend or database — the front end is hand-written HTML + vanilla JS loading pre-generated data files. (The *data-generation* layer does use a local SQLite DB, `tw_volume.db` — see "Data generation" below; it never ships to the site.)

> Historically the daily Excel came from a partner. It is now produced on this machine by `volume_system.py` + `bsr_fetch.py` + `tpex_fetch.py`. **The full daily runbook is in [`每日更新流程.md`](每日更新流程.md)** — read it for the exact step-by-step.

Live site: https://tongwade.github.io/stock-daily/ — Repo: `tongwade/stock-daily`. **Pushing to `main` triggers the `Deploy site to GitHub Pages` workflow (`.github/workflows/pages.yml`), which publishes `site/`.** The earlier Cloudflare Pages + `wrangler` Direct Upload flow (and its Cloudflare Access login) has been **superseded** by this git-driven workflow — do not run `wrangler` to deploy.

### Local environment (this machine)
- **Use Python 3.13 at `C:\Users\tongw\AppData\Local\Programs\Python\Python313\python.exe`** — NOT the default `python` (Miniconda 3.9, which can't build `greenlet`/`patchright` and hits ProgramData permission errors). Deps installed there: `openpyxl requests ddddocr patchright pandas numpy`.
- **Node** at `C:\Program Files\nodejs\node.exe` (not on PATH; use the full path, or open a fresh terminal).
- System **Chrome** (for `tpex_fetch.py`) at `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`.

## Commands

`$PY` below = the Python 3.13 full path above; `$NODE` = the Node full path. (`python`/`node` bare names won't work on this machine — see "Local environment".)

```bash
# --- Data generation (upstream of build.py) ---
# Market signals (放量/延續/出關/處置/勝率) → out/台股放量訊號_YYYYMMDD.xlsx
$PY volume_system.py --update            # daily; auto-uses latest trading day in the DB
$PY volume_system.py --init              # FIRST TIME ONLY: backfill ~7 months into tw_volume.db

# Per-stock 分點 (broker buy/sell) → data/YYYYMMDD/{code}_bsr.csv
$PY bsr_fetch.py 2344 3037 6257 --date YYYYMMDD     # 上市/TWSE (ddddocr captcha)
$PY tpex_fetch.py 3105 6261 --date YYYYMMDD          # 上櫃/TPEX (patchright + real Chrome, Turnstile)

# --- Build & publish ---
$PY build.py                  # Regenerate site data from data/ (skips already-built dates)
$PY build.py --force          # Force full rebuild (use after changing build.py logic)
$NODE site/smoke.js site      # Headless smoke test: stubs DOM/gridjs/Chart, renders every date/stock/week
git add -A && git commit -m "..." && git push     # Deploy: push to main → GitHub Actions publishes site/
gh run list --limit 1         # Verify the deploy ("Deploy site to GitHub Pages" = success)

# Local preview: just open site/index.html in a browser (works over file:// — see .js-wrapper note).
```

Python deps (in the Python 3.13 env): `openpyxl requests ddddocr patchright pandas numpy`. The smoke test needs Node.

## Daily update workflow

Run after market close on a trading day. Full runbook: [`每日更新流程.md`](每日更新流程.md). In short:

1. `$PY volume_system.py --update` → produces `out/台股放量訊號_<date>.xlsx` (market signals).
2. `$PY bsr_fetch.py 2344 3037 6257 --date <date>` and `$PY tpex_fetch.py 3105 6261 --date <date>` → per-stock 分點 CSVs into `data/<date>/`.
3. Copy `out/台股放量訊號_<date>.xlsx` into `data/<date>/`.
4. `$PY build.py` (only processes dates not yet built).
5. `$NODE site/smoke.js site` to confirm no render errors.
6. `git add -A && git commit -m "..." && git push` → GitHub Actions publishes to GitHub Pages. Confirm with `gh run list --limit 1`.

> **Run it every trading day, in order, without skipping** — `volume_system.py` is stateful/accumulating (see below). Skipped days break the 量能延續 chain and leave gaps in 勝率回測.

## Architecture

Three-stage pipeline: **(crawlers) → Excel/CSV → (build.py) → site/data/*.js → (static front end) → GitHub Pages**.

### Data generation (upstream of build.py)
- **`volume_system.py`** — the 大盤放量訊號 engine. Fetches whole-market TWSE/TPEx daily price/volume into a **SQLite DB `tw_volume.db`**, detects 放量訊號 / 出關 / 量能延續 / 處置 / 勝率回測, and exports `out/台股放量訊號_YYYYMMDD.xlsx`.
  - `--init` (first time): backfill ~7 months. `--update` (daily): fetch latest trading day, detect, export. `--backfill YYYYMMDD`: write one day's *signals* only.
  - **`tw_volume.db` is critical, stateful, accumulated state** (~92MB, git-ignored). It is **irreplaceable** — a fresh `--init` does NOT rebuild historical signals or 勝率回測 tracking (those only accumulate by running `--update` every day). **Back it up** (e.g. weekly zip to cloud). Don't delete it. `tw_volume_full.db` is a kept snapshot/backup.
  - **量能延續 is a chain**: day N's continuation = day N-1's (`signals` ∪ `continuation_tracking`). Skipping a day, or backfilling only signals (not continuation), leaves gaps. To repair a middle day you must run `detect_continuation` for it, then re-run the next day.
  - **TWSE silent-drop gotcha**: `fetch_twse_day()` returns empty (no error/log) on a rate-limited non-OK response. A rapid `--init` can thus store **only 上櫃 (TPEX)** and zero 上市 (TWSE). Symptom: 放量訊號 all-TPEX. Fix: re-run `--update`, or use `backfill_twse.py` (per-day fetch + retry) — check coverage via `daily_volume.market`, **not** a JOIN to `stock_info` (INSERT-OR-REPLACE can flip a cross-market code's label).
- **`bsr_fetch.py`** — 上市 (TWSE) per-stock 分點 from the BSR site (solves the 5-char captcha with `ddddocr`). Reads ALL records (both left+right CSV columns; Σbuy≈Σsell when complete). Output: `data/YYYYMMDD/{code}_bsr.csv`.
- **`tpex_fetch.py`** — 上櫃 (TPEX) per-stock 分點 from TPEx brokerBS, behind Cloudflare Turnstile. Uses **patchright + system Chrome + a persistent profile** (`.patchright_profile/`, holds `cf_clearance`) to auto-pass Turnstile. **Needs a desktop + residential IP** (won't pass on datacenter/CI IPs). Output: same `{code}_bsr.csv` format.
- Helpers: `backfill_twse.py` (one-off TWSE history backfill), `verify_data.py` / `fetch_verify.py` (cross-check JSON vs raw, and量價 vs TWSE/TPEx APIs). `日報.py` / `量價分析插入png圖彙總.py` are the partner's original per-stock analysis scripts — kept for reference; `build.py`'s `process_stock_from_bsr` now computes the equivalent directly from the BSR CSV.

### build.py (Excel/CSV → data files)
- Scans `data/YYYYMMDD/` folders. Files are classified by name in `classify()`:
  - `台股放量訊號*.xlsx` → market file (sheets: 今日放量訊號, 量能延續追蹤, 出關股追蹤, 處置股清單, 勝率回測) → `site/data/YYYYMMDD/market.json`
  - `{code}_bsr.csv` → **preferred** per-stock source (from the crawlers above): `process_stock_from_bsr` computes buy_top/sell_top/price_volume/broker_detail directly from the full 分點 records.
  - `{code}*日報*.xlsx` / `{code}*分析結果*.xlsx` → legacy per-stock fallbacks (broker top-20; price/volume + ~12k-row broker detail) used when no BSR CSV is present.
  - `{code}*charts*.xlsx` files are **ignored** — the 6 technical charts are now drawn live by Chart.js from the broker buy/sell/detail data, so no PNGs are extracted or stored.
- Per-stock output merged into `site/data/YYYYMMDD/{code}.json`.
- **Weekly (週報)**: a week = **Fri → next Thu** (aligns with the 集保 股權分散表 weekly stats period, which runs Fri→next Thu). Two ways it lands in `site/data/weekly/<wkey>/`:
  - `build_weekly_from_daily.py --current` (**preferred, run daily**) or `... <wkey>` aggregates the existing daily `site/data/<date>/{code}.json` 分點 across the Fri→Thu window into `{code}.json` (買賣超前20) + `{code}_vol.json` (大量與均價: 大量價=當日買進量最大價位; top10 量=日 buy_top/sell_top 前10 加總; top10 均價=前10均價的**未加權平均**; 收盤價取自 `tw_volume.db`). `--current` auto-builds the latest trading day's Fri→Thu week (partial if <5 days; fills in as days arrive; prunes stale same-week buckets). wkey = 涵蓋的最早-最晚交易日 (e.g. `20260529-0604` full week; `20260605-0605` in-progress). Validate with `--check <wkey>`.
  - Legacy: `data/weekly/YYYYMMDD-MMDD/` Excel → `classify_weekly` → `process_weekly` + `process_volume_avg` (partner's `*週報*.xlsx` / `*大量與均價*.xlsx`).
  - Either way `index.json` gets a `weekly_dates` list with the same merge-protection as daily dates; `build.py` emits the `.js` wrappers and updates the index.
- Generates `site/data/index.json` — the date list + which stocks each date has (each stock entry: `code`, `name`, `mkt`); the front end builds all menus from this.
- **Index is merged, not overwritten** (`load_existing_index()` + merge in `main()`): dates freshly built from raw `data/` win, but any existing date still present as a `site/data/YYYYMMDD/` folder is **kept** even if its raw Excel is absent. This prevents a collaborator who only has *some* days' raw Excel locally from wiping the other dates out of the menu when they rebuild. (This exact bug happened 2026-06-04.)
- `mkt` is the Yahoo market suffix per stock — `TW` (上市/TWSE) or `TWO` (上櫃/TPEX), used by the front end to build the Yahoo technical-analysis link. `build_market_map`/`build_global_market_map` read it from the market file's 市場 column; `normalize_markets()` then unifies across all days (any day tagged `TWO` wins) since a stock's market is stable — so a partial rebuild can't mislabel it.
- New stocks/dates need **no code changes** — they are auto-detected. Stock display names come from `stock_names.json` (code→name overrides), falling back to names in the market file.
- `SKIP_EXISTING` (default true; `--force` disables) skips dates whose output JSON already parses correctly.

### The .js wrapper trick (important)
`emit_js_wrappers()` writes a `.js` copy of every `.json` that calls `window.__DATAREG(key, data)`. The front end (`app.js` `loadData()`) loads data by injecting `<script src="data/KEY.js">` tags, **not** fetch — so the site works when opened directly via `file://` with no web server. Consequences:
- The deployed/used data files are the **`.js`** ones. The `.json` files are intermediate products and are git-ignored by `site/.gitignore` (`data/**/*.json`). Do not expect `data/index.json` to exist on the live site — use `data/index.js`.
- Any new data file produced by hand must follow the same `window.__DATAREG(...)` wrapper format.
- **`index.js` cache-busting**: `loadData()` appends `?t=<timestamp>` **only** for the `index` key and **only** over http(s) (not `file://`). The date list changes on every update but is loaded via a plain `<script>` tag, and GitHub Pages serves it with `Cache-Control: max-age=600` — without the buster, new dates wouldn't show for up to 10 min (this caused a "missing dates" report on 2026-06-04). Per-date data files are immutable, so they are intentionally left cacheable.

### Front end (site/)
- `index.html` — tab views: 大盤放量訊號, 量能延續追蹤, 出關股追蹤, 處置股清單, 勝率回測, 個股分析, 週報分析, 使用說明. A date `<select>` switches the active day; the 週報 view has its own week `<select>`.
- `app.js` — vanilla JS. `cache`/`pending` registry feeds the `__DATAREG` loader. Renderers: `renderMarket`/`renderContinuation`/`renderRelease`/`renderDisposed` (Grid.js tables), `renderWinrate` (Chart.js bar + tables), `renderStock`/`loadStock` (price/volume Chart.js, detail Grid.js), `renderBrokerCharts` (6 technical charts from `buy_top`/`sell_top`/`broker_detail`), `renderWeekly`/`loadWeeklyStock`/`renderBrokerChartsWeekly` (週報). When `app.js` changes, bump the `?v=` cache-buster on its `<script>` tag in `index.html`.
- Third-party libs (Grid.js, Chart.js) load from CDN via `<script>` in `index.html`.
- **`site/smoke.js`** — the smoke test. It is **git-ignored** (`site/.gitignore`), so a fresh clone won't have it; it was rebuilt 2026-06-07. It stubs `document`/`gridjs`/`Chart`, evals `app.js`, then drives every date×tab×stock and week×stock via the wired event handlers to catch runtime errors. Because `gridjs`/`Chart` are stubbed, it catches *app.js* logic errors but **not** third-party internals — e.g. a benign "Grid.js: Cannot read properties of undefined (reading 'length')" appears only in a real browser and is pre-existing noise, not a smoke failure.

### Deployment
- **Active path: GitHub Pages via GitHub Actions.** `.github/workflows/pages.yml` (`Deploy site to GitHub Pages`) runs on every push to `main` (and `workflow_dispatch`); it uploads `site/` as a Pages artifact and deploys it to https://tongwade.github.io/stock-daily/. **To publish: just `git push` to `main`.** Confirm the run with `gh run list --limit 1` (status `success`); inspect the live data with e.g. `curl -s https://tongwade.github.io/stock-daily/data/index.js`.
- **Superseded: Cloudflare Pages + `wrangler`.** The site was previously published to Cloudflare Pages (project `stock-daily`, `stock-daily-s6v.pages.dev`) by Direct Upload (`npx wrangler pages deploy site --project-name stock-daily`), behind a Cloudflare Access login. That flow has been replaced by the GitHub Actions workflow above — **do not run `wrangler` to deploy.** (Older still: `site/deploy.bat`, a branch-based approach, also unused.)

## Gotchas

- **Nested git repo**: `site/.git` exists as a leftover from `deploy.bat`'s design, separate from the root repo that actually deploys. Run git commands from the repo **root** (`stock/`); git commands inside `site/` act on the stale nested repo and won't affect the live site.
- **Raw data is not deployed**: root `data/`, `out/`, `tw_volume.db*`, `*.log` are all git-ignored (see `.gitignore`). Only the processed `site/data/` is published. Keep `data/` and the DB locally to allow rebuilds.
- Excel parsing relies on locating a header row containing a key column (代號 / 分類 / 股價) via `find_header`; if a source file's layout changes, parsing silently returns empty records rather than erroring.
- **Data generation can't run in cloud CI / Claude routines.** Two hard blockers: (1) `tw_volume.db` is large accumulated state that ephemeral cloud runners don't persist; (2) `tpex_fetch.py`'s Cloudflare Turnstile won't pass on datacenter IPs — it needs a real desktop Chrome on a residential IP. Automate via **local Windows Task Scheduler** (or a self-hosted runner), not GitHub-hosted Actions / remote routines. Only the *deploy* half (push → Pages) is cloud CI.
