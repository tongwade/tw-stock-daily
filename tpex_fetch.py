#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tpex_fetch.py — 抓「上櫃(TPEx)」個股券商分點進出明細。

上櫃資料在 TPEx 的 brokerBS 頁，且受 Cloudflare Turnstile（「我不是機器人」）保護。
過去 headful 的內建 Chromium 可被 Turnstile 自動放行，但 Cloudflare 已收緊偵測：
內建 Chromium 連挑戰 iframe 都不渲染、token 永遠是空的，查詢自然送不出去。

現行解法（2026-06 起）：改用 **patchright**（Playwright 的修補版，消除 Cloudflare 用來
偵測自動化的 CDP 痕跡，例如 Runtime.enable 洩漏）＋ 系統真 Chrome（channel="chrome"）
＋ 持久化使用者設定檔（保存 cf_clearance，第二次起更快）。實測 Turnstile 約 5~12 秒
**自動**產生 token，無需人工點選。

取得資料的方式：頁面查詢結果是分頁 HTML 表格（不完整），但表單內有「下載 CSV」按鈕，
按下會回傳**完整**單表 CSV。注意 **Turnstile token 是一次性**的——必須在拿到 token 後
「直接」按下載鈕，不可先按「查詢」把 token 用掉，否則會下載到 0 byte 空檔。

下載到的 CSV 第 3 行起為「序號,券商,價格,買進股數,賣出股數」單欄表，轉成與 BSR 相同格式
的乾淨 CSV（序號,券商,股價,買進股數,賣出股數），build.py / 下游可直接吃。

前置：
    pip install patchright
    python -m patchright install chromium     # 或確保系統已裝 Google Chrome
用法（需「有桌面」環境，會跳出瀏覽器視窗；--hide 可把視窗移到螢幕外給排程用）：
    python tpex_fetch.py 3105 6261
    python tpex_fetch.py --hide 3105 6261
產出：每檔 {code}_bsr.csv（序號,券商,股價,買進股數,賣出股數）＋ {code}_tpex_raw.csv（原始下載）
"""
import os, re, csv, sys, io, time, argparse, datetime

PAGE = "https://www.tpex.org.tw/zh-tw/mainboard/trading/info/brokerBS.html"
PROFILE_DIRNAME = ".patchright_profile"   # 持久化設定檔（存 cf_clearance，加速 Turnstile）


def _to_int(x):
    x = str(x or "").replace(",", "").strip().strip('"')
    if not x:
        return 0
    try:
        return int(float(x))
    except ValueError:
        return 0


def parse_tpex_csv(csv_text):
    """解析 TPEx 下載的券商買賣 CSV。
    格式：前兩行為標題（券商買賣證券成交價量資訊 / 證券代碼,xxxx），
          第三行為表頭「序號,券商,價格,買進股數,賣出股數」，其後為資料列。
    回傳 list[dict]：序號 / 券商 / 股價 / 買進股數 / 賣出股數。"""
    out = []
    started = False
    for r in csv.reader(io.StringIO(csv_text)):
        if not r:
            continue
        if not started:
            if r[0].strip() == "序號":       # 找到表頭列後才開始讀資料
                started = True
            continue
        if len(r) < 5 or not r[0].strip().isdigit():
            continue
        out.append({
            "序號": _to_int(r[0]),
            "券商": r[1].strip(),
            "股價": r[2].strip().strip('"'),
            "買進股數": _to_int(r[3]),
            "賣出股數": _to_int(r[4]),
        })
    return out


def _wait_turnstile(page, timeout_s=45):
    """等 Turnstile 自動產生 token（patchright 多半 5~12 秒）。回傳 token 字串（逾時為空字串）。"""
    deadline = timeout_s * 2
    for _ in range(deadline):
        try:
            tok = page.eval_on_selector(
                "input[name='cf-turnstile-response']", "e=>e&&e.value") or ""
        except Exception:
            tok = ""
        if tok:
            return tok
        time.sleep(0.5)
    return ""


def fetch_one(ctx, code, raw_dir):
    """在持久化 context 開新分頁查一檔：等 Turnstile → 直接下載 CSV → 解析。
    回傳 (records | None, err)；err 為 None 表成功。"""
    page = ctx.new_page()
    try:
        page.goto(PAGE, wait_until="domcontentloaded", timeout=45000)
        time.sleep(1.5)
        page.fill("input.code", str(code))
        tok = _wait_turnstile(page)
        if not tok:
            return None, "turnstile-timeout（Turnstile 未自動過，可能需更新 patchright 或手動點一次）"
        # token 一次性：拿到後「直接」按下載 CSV(UTF-8)，不可先按查詢
        with page.expect_download(timeout=25000) as dl_info:
            page.click("#tables-form button.response[data-format='utf-8']", timeout=8000)
        dl = dl_info.value
        data = open(dl.path(), "rb").read()
        txt = data.decode("utf-8-sig", "replace")
        # 存原始下載供除錯/校正
        with open(os.path.join(raw_dir, f"{code}_tpex_raw.csv"), "w",
                  encoding="utf-8-sig", newline="") as f:
            f.write(txt)
        if len(data) < 100:
            return None, f"下載檔過小({len(data)} bytes)，可能 token 失效或當日無資料"
        return parse_tpex_csv(txt), None
    finally:
        page.close()


def save_csv(records, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["序號", "券商", "股價", "買進股數", "賣出股數"])
        w.writeheader(); w.writerows(records)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="+")
    ap.add_argument("--out", default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--keep-open", action="store_true", help="跑完不關視窗（除錯用）")
    ap.add_argument("--hide", action="store_true",
                    help="把瀏覽器視窗移到螢幕外（排程無人值守用；視窗仍真實存在，Turnstile 照過）")
    args = ap.parse_args()

    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        print("缺少 patchright，請先安裝：pip install patchright 並 python -m patchright install chromium",
              flush=True)
        sys.exit(2)

    root = os.path.dirname(os.path.abspath(__file__))
    date = args.date or datetime.date.today().strftime("%Y%m%d")
    out_dir = args.out or os.path.join(root, "data", date)
    os.makedirs(out_dir, exist_ok=True)
    profile = os.path.join(root, PROFILE_DIRNAME)

    print(f"TPEx(上櫃) 抓取 {len(args.codes)} 檔 → {out_dir}", flush=True)
    ok = 0; failed = []
    with sync_playwright() as p:
        launch_args = []
        if args.hide:   # 視窗移到螢幕外，無人值守時不打擾（仍是真實 headful，Turnstile 可過）
            launch_args += ["--window-position=-32000,-32000", "--window-size=1100,800"]
        ctx = p.chromium.launch_persistent_context(
            profile, channel="chrome", headless=False, no_viewport=True,
            accept_downloads=True, args=launch_args)
        try:
            for code in args.codes:
                try:
                    recs, err = fetch_one(ctx, code, out_dir)
                except Exception as e:
                    print(f"  {code}: 例外 {type(e).__name__}: {e}", flush=True)
                    failed.append(code); continue
                if err:
                    print(f"  {code}: {err}", flush=True)
                    failed.append(code); continue
                if not recs:
                    print(f"  {code}: 解析不到資料（raw 已存）", flush=True)
                    failed.append(code); continue
                buy = sum(r["買進股數"] for r in recs); sell = sum(r["賣出股數"] for r in recs)
                balanced = abs(buy - sell) <= max(50, buy * 0.001)
                save_csv(recs, os.path.join(out_dir, f"{code}_bsr.csv"))
                print(f"  {code}: {len(recs)} 筆，Σ買={buy:,} Σ賣={sell:,} "
                      f"{'OK' if balanced else '[!] 買賣不平衡(資料可能不完整)'}", flush=True)
                ok += 1
                time.sleep(1.0)
            if args.keep_open:
                print("（--keep-open）視窗保留中，按 Enter 關閉…", flush=True)
                try: input()
                except Exception: pass
        finally:
            ctx.close()
    print(f"完成 {ok}/{len(args.codes)}" + (f"；失敗：{','.join(failed)}" if failed else ""), flush=True)
    sys.exit(0 if ok == len(args.codes) else 1)


if __name__ == "__main__":
    main()
