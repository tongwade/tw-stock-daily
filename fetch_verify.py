#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_verify.py — 獨立的「線上抓取 + 與原始 Excel 比對」工具（不沿用 build.py）。

用途
----
反推出的資料來源：
  * 「台股放量訊號」的量價基礎  → TWSE / TPEx 每日個股成交資訊（免金鑰、公開）
  * 個股「日報 / 分析結果」的券商分點 → TWSE 券商買賣日報表(BSR, bsr.twse.com.tw)
        ⚠️ BSR 有圖形驗證碼且僅當日可查，無法用乾淨 API 自動抓，故本工具不處理該層。

本工具只驗證「可由公開 API 乾淨取得」的量價層：
  讀取 data/YYYYMMDD/台股放量訊號_*.xlsx 的「今日放量訊號」工作表，
  逐檔上線抓當日量價，比對  收盤價 / 當日量(張) / 漲跌幅%  是否一致。

用法
----
  python fetch_verify.py 20260602            # 取樣前 15 檔比對
  python fetch_verify.py 20260602 --all       # 全部比對（量大、較慢）
  python fetch_verify.py 20260602 --limit 30  # 自訂取樣檔數
  python fetch_verify.py 20260602 --codes 2382,3231,3105  # 只比對指定代號
"""
import os, re, sys, json, ssl, time, glob, argparse, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"}


# ---------- 基本工具 ----------
def _get(url, timeout=20, retries=3, backoff=1.2):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(backoff * (attempt + 1))
    raise last


def _num(x):
    """把 '1,234'、'+7.52%'、'--' 之類轉成 float，失敗回 None。"""
    if x is None:
        return None
    s = str(x).strip().replace(",", "").replace("%", "").replace("+", "")
    if s in ("", "--", "---", "X", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def roc_ad(yyyymmdd):
    """20260602 -> (西元 '2026/06/02', 民國 '115/06/02')。"""
    y, m, d = int(yyyymmdd[:4]), yyyymmdd[4:6], yyyymmdd[6:8]
    return f"{y}/{m}/{d}", f"{y - 1911}/{m}/{d}"


# ---------- 來源 A：上市 TWSE ----------
def fetch_twse(stockno, yyyymmdd):
    """回傳 {close, vol_lots, chg} 或 None。當日量(張)=成交股數/1000(四捨五入)。"""
    url = (f"https://www.twse.com.tw/exchangeReport/STOCK_DAY"
           f"?response=json&date={yyyymmdd}&stockNo={stockno}")
    d = None
    for attempt in range(4):
        try:
            d = json.loads(_get(url))
        except Exception as e:
            return {"error": f"net:{type(e).__name__}"}
        if d.get("stat") == "OK":
            break
        # 偶發限流錯誤（會謊報日期過舊）→ 稍候重試
        time.sleep(1.5 * (attempt + 1))
    if not d or d.get("stat") != "OK":
        return {"error": d.get("stat", "no-data") if d else "no-data"}
    _, roc = roc_ad(yyyymmdd)
    for row in d.get("data", []):
        if str(row[0]).strip() == roc:
            shares = _num(row[1])      # 成交股數
            close = _num(row[6])       # 收盤價
            diff = _num(row[7])        # 漲跌價差（含正負）
            chg = None
            if close is not None and diff is not None and (close - diff) not in (0, None):
                chg = round(diff / (close - diff) * 100, 2)
            return {"close": close,
                    "vol_lots": None if shares is None else round(shares / 1000),
                    "chg": chg}
    return {"error": "date-not-found"}


# ---------- 來源 B：上櫃 TPEx ----------
# 用「全市場每日收盤行情(otc)」整日一次抓、快取查表。其欄位「成交股數」÷1000
# 即為放量訊號採用的當日量(張)；單檔 tradingStock 的「成交張數」含盤後/零股會偏高。
_TPEX_CACHE = {}   # {yyyymmdd: {code: {close, vol_lots, chg}}}


def _load_tpex_day(yyyymmdd):
    if yyyymmdd in _TPEX_CACHE:
        return _TPEX_CACHE[yyyymmdd]
    ad, _ = roc_ad(yyyymmdd)
    url = (f"https://www.tpex.org.tw/www/zh-tw/afterTrading/otc"
           f"?date={ad}&type=EW&id=&response=json")
    table = {}
    try:
        d = json.loads(_get(url))
        rows = (d.get("tables") or [{}])[0].get("data", [])
        for row in rows:
            code = str(row[0]).strip()
            close = _num(row[2])       # 收盤
            diff = _num(row[3])        # 漲跌（含正負號）
            shares = _num(row[7])      # 成交股數
            chg = None
            if close is not None and diff is not None and (close - diff) not in (0, None):
                chg = round(diff / (close - diff) * 100, 2)
            table[code] = {"close": close,
                           "vol_lots": None if shares is None else round(shares / 1000),
                           "chg": chg}
    except Exception as e:
        _TPEX_CACHE[yyyymmdd] = {"__error__": f"net:{type(e).__name__}"}
        return _TPEX_CACHE[yyyymmdd]
    _TPEX_CACHE[yyyymmdd] = table
    return table


def fetch_tpex(stockno, yyyymmdd):
    """回傳 {close, vol_lots, chg} 或 {error}。"""
    table = _load_tpex_day(yyyymmdd)
    if "__error__" in table:
        return {"error": table["__error__"]}
    hit = table.get(str(stockno).strip())
    return hit if hit else {"error": "code-not-found"}


def fetch_quote(stockno, market, yyyymmdd):
    return fetch_tpex(stockno, yyyymmdd) if str(market).upper().startswith("TPE") \
        else fetch_twse(stockno, yyyymmdd)


# ---------- 讀原始 Excel 的「今日放量訊號」----------
def read_signal_sheet(yyyymmdd):
    import openpyxl
    ddir = os.path.join(DATA_DIR, yyyymmdd)
    cands = glob.glob(os.path.join(ddir, "台股放量訊號*.xlsx"))
    if not cands:
        sys.exit(f"找不到 {ddir} 下的 台股放量訊號*.xlsx")
    wb = openpyxl.load_workbook(cands[0], data_only=True, read_only=True)
    ws = wb["今日放量訊號"]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    # 找表頭列（含「代號」）
    hi = next((i for i, r in enumerate(rows)
               if any(str(c).strip() == "代號" for c in r if c is not None)), None)
    if hi is None:
        sys.exit("今日放量訊號 找不到表頭")
    header = [str(c).strip() if c is not None else "" for c in rows[hi]]
    idx = {name: header.index(name) for name in
           ["代號", "股票名稱", "市場", "收盤價", "漲跌幅%", "當日量(張)"] if name in header}
    out = []
    for r in rows[hi + 1:]:
        if not r or r[idx["代號"]] is None:
            continue
        code = str(r[idx["代號"]]).strip()
        if not re.fullmatch(r"\d{4,6}", code):
            continue
        out.append({
            "code": code,
            "name": str(r[idx["股票名稱"]]).strip() if "股票名稱" in idx else "",
            "market": str(r[idx["市場"]]).strip() if "市場" in idx else "",
            "close": _num(r[idx["收盤價"]]) if "收盤價" in idx else None,
            "chg": _num(r[idx["漲跌幅%"]]) if "漲跌幅%" in idx else None,
            "vol_lots": _num(r[idx["當日量(張)"]]) if "當日量(張)" in idx else None,
        })
    return os.path.basename(cands[0]), out


# ---------- 比對 ----------
def approx(a, b, tol):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="YYYYMMDD，需存在於 data/ 下")
    ap.add_argument("--limit", type=int, default=15, help="取樣比對檔數（預設 15）")
    ap.add_argument("--all", action="store_true", help="比對全部")
    ap.add_argument("--codes", help="只比對指定代號，逗號分隔")
    ap.add_argument("--sleep", type=float, default=0.4, help="每次請求間隔秒數")
    args = ap.parse_args()

    fname, sig = read_signal_sheet(args.date)
    print(f"原始檔: {fname}　今日放量訊號共 {len(sig)} 檔")

    if args.codes:
        want = {c.strip() for c in args.codes.split(",")}
        sample = [s for s in sig if s["code"] in want]
    elif args.all:
        sample = sig
    else:
        sample = sig[:args.limit]
    print(f"本次比對 {len(sample)} 檔（來源：TWSE/TPEx 每日個股成交資訊）\n")

    hdr = f'{"代號":<7}{"名稱":<8}{"市場":<6}{"欄位":<10}{"原始Excel":>14}{"線上API":>14}  判定'
    print(hdr)
    print("-" * len(hdr))
    mism = 0
    netfail = 0
    checked = 0
    for s in sample:
        q = fetch_quote(s["code"], s["market"], args.date)
        time.sleep(args.sleep)
        if q is None or q.get("error"):
            netfail += 1
            print(f'{s["code"]:<7}{s["name"]:<8}{s["market"]:<6}{"(抓取失敗)":<10}{"":>14}{"":>14}  ! {q.get("error") if q else "none"}')
            continue
        # 收盤價(±0.001)、當日量張(±1 張容差)、漲跌幅(±0.05%)
        comps = [
            ("收盤價", s["close"], q["close"], 0.001),
            ("當日量(張)", s["vol_lots"], q["vol_lots"], 1),
            ("漲跌幅%", s["chg"], q["chg"], 0.05),
        ]
        for field, ev, av, tol in comps:
            ok = approx(ev, av, tol)
            checked += 1
            if not ok:
                mism += 1
            mark = "✓" if ok else "✗ 不一致"
            evs = "" if ev is None else f"{ev:,.2f}" if field != "當日量(張)" else f"{ev:,.0f}"
            avs = "" if av is None else f"{av:,.2f}" if field != "當日量(張)" else f"{av:,.0f}"
            print(f'{s["code"]:<7}{s["name"]:<8}{s["market"]:<6}{field:<10}{evs:>14}{avs:>14}  {mark}')

    print("\n" + "=" * 50)
    print(f"比對欄位數: {checked}　不一致: {mism}　抓取失敗檔數: {netfail}")
    if mism == 0 and netfail == 0:
        print("結論：抓到的量價與原始 Excel 完全一致 ✓")
    elif mism == 0:
        print("結論：成功抓到的部分全部一致；有少數檔線上抓取失敗（見上）。")
    else:
        print("結論：發現不一致，請見上方 ✗ 標記。")


if __name__ == "__main__":
    main()
