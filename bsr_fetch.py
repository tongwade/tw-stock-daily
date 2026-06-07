#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bsr_fetch.py — 自動從 TWSE「券商買賣日報表 BSR」抓取個股分點進出明細。

來源：https://bsr.twse.com.tw/bshtm/  （官方、免費，但有圖形驗證碼、僅當日可查）
本工具用 ddddocr 自動辨識 5 碼英數驗證碼，辨識率約 6~7 成，錯了就換一張重試，
配合重試後實務上等於穩定取得。

⚠️ 重要：BSR 原始 CSV 是「左右雙欄」排列（序號 1,3,5… 在左半，2,4,6… 在右半）。
   必須左右合併才完整（Σ買進股數 == Σ賣出股數）。本工具讀「全部」紀錄，
   修正了舊流程 usecols=[0,1,2,3,4] 只讀左半、漏掉約一半紀錄的問題。

用法：
    python bsr_fetch.py 2330 2344 3037           # 抓多檔，輸出乾淨 CSV 到 data/今天/
    python bsr_fetch.py --out D:/tmp 2330         # 指定輸出資料夾
產出：每檔一個 {code}_bsr.csv（欄位：序號,券商,股價,買進股數,賣出股數；UTF-8-SIG）
"""
import os, re, csv, sys, time, io, argparse, datetime
import requests
import urllib3
import ddddocr

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://bsr.twse.com.tw/bshtm/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

_OCR = None
def _ocr():
    global _OCR
    if _OCR is None:
        _OCR = ddddocr.DdddOcr(show_ad=False)
    return _OCR


def _hidden(html, name):
    m = re.search(r'id="%s" value="([^"]*)"' % re.escape(name), html)
    return m.group(1) if m else ""


_NO_DATA = "__NO_DATA__"   # 該股當日無 BSR 資料的標記（與「抓取失敗」區分）


def _is_image(b):
    """魔術位元組判斷是否為真圖片（PNG/GIF/JPEG）。限流時伺服器會回非圖片擋頁。"""
    return b[:8].startswith((b"\x89PNG", b"GIF8", b"\xff\xd8"))


def fetch_bsr_csv(code, max_tries=12, pause=0.8, verbose=True):
    """解驗證碼並下載某代號的 BSR 原始 CSV（big5 解碼後的字串）。
    回傳 CSV 字串／_NO_DATA（當日無資料）／None（重試耗盡或被限流）。"""
    code = str(code).strip()
    ocr = _ocr()
    throttle = 0
    for i in range(1, max_tries + 1):
        try:
            s = requests.Session(); s.headers.update(UA)
            html = s.get(BASE + "bsMenu.aspx", timeout=20, verify=False).text
            guid = re.search(r"CaptchaImage\.aspx\?guid=([0-9a-f-]+)", html)
            if not guid:
                time.sleep(pause); continue
            img = s.get(BASE + "CaptchaImage.aspx?guid=" + guid.group(1),
                        timeout=20, verify=False).content
            if not _is_image(img):       # 被限流：拿到非圖片擋頁 → 退避後重試
                throttle += 1
                wait = min(30, 3 * throttle)
                if verbose:
                    print(f"  [{code}] try{i}: 疑似限流(非圖片)，等 {wait}s", flush=True)
                time.sleep(wait); continue
            cap = re.sub(r"[^0-9A-Za-z]", "", ocr.classification(img)).upper()
            if len(cap) != 5:            # BSR 必為 5 碼，長度不對直接換一張
                continue
            data = {
                "__EVENTTARGET": "", "__EVENTARGUMENT": "", "__LASTFOCUS": "",
                "__VIEWSTATE": _hidden(html, "__VIEWSTATE"),
                "__VIEWSTATEGENERATOR": _hidden(html, "__VIEWSTATEGENERATOR"),
                "__EVENTVALIDATION": _hidden(html, "__EVENTVALIDATION"),
                "RadioButton_Normal": "RadioButton_Normal",
                "TextBox_Stkno": code,
                "CaptchaControl1": cap,
                "btnOK": "查詢",
            }
            r = s.post(BASE + "bsMenu.aspx", data=data, timeout=20, verify=False)
            m = re.search(r'id="HyperLink_DownloadCSV"\s+href="([^"]+)"', r.text)
            if m:
                href = m.group(1).replace("&amp;", "&")
                csv_bytes = s.get(BASE + href, timeout=40, verify=False).content
                if verbose:
                    print(f"  [{code}] try{i}: captcha {cap} OK, CSV {len(csv_bytes)} bytes", flush=True)
                return csv_bytes.decode("big5", "replace")
            # 沒下載連結：成功頁與無資料頁「都」含 CaptchaImage，故改用「查無資料」字串判定。
            if "查無資料" in r.text:
                if verbose:
                    print(f"  [{code}] try{i}: captcha {cap} 正確，但 BSR 查無當日資料", flush=True)
                return _NO_DATA
            if verbose:
                print(f"  [{code}] try{i}: captcha {cap} 未過，換一張", flush=True)
            time.sleep(pause); continue
        except Exception as e:
            if verbose:
                print(f"  [{code}] try{i}: error {type(e).__name__}", flush=True)
            time.sleep(pause)
    return None


def _num(x):
    x = str(x).replace(",", "").strip()
    if not x:
        return 0
    try:
        return int(x)
    except ValueError:
        return 0


def parse_bsr(csv_text):
    """把 BSR 原始雙欄 CSV 解析成乾淨單表紀錄（左右半都讀）。
    回傳 list[dict]：序號 / 券商 / 股價 / 買進股數 / 賣出股數。"""
    rows = list(csv.reader(io.StringIO(csv_text)))
    out = []
    for r in rows:
        if not r or not r[0].strip().isdigit():
            continue
        # 左半：1=券商 2=股價 3=買 4=賣
        if len(r) >= 5 and r[1].strip():
            out.append({"序號": _num(r[0]), "券商": r[1].strip(),
                        "股價": r[2].strip(), "買進股數": _num(r[3]), "賣出股數": _num(r[4])})
        # 右半：6=序號 7=券商 8=股價 9=買 10=賣
        if len(r) >= 11 and r[6].strip().isdigit() and r[7].strip():
            out.append({"序號": _num(r[6]), "券商": r[7].strip(),
                        "股價": r[8].strip(), "買進股數": _num(r[9]), "賣出股數": _num(r[10])})
    return out


def fetch_records(code, **kw):
    """抓取 + 解析，回傳乾淨紀錄 list；無資料回 _NO_DATA；失敗回 None。"""
    txt = fetch_bsr_csv(code, **kw)
    if txt is None or txt is _NO_DATA:
        return txt
    return parse_bsr(txt)


def save_csv(records, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["序號", "券商", "股價", "買進股數", "賣出股數"])
        w.writeheader()
        w.writerows(records)


def main():
    # 排程多半把輸出導到 log；統一用 utf-8 避免 cp950 終端遇非 Big5 字元崩潰
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="+", help="股票代號，可多檔")
    ap.add_argument("--out", default=None, help="輸出資料夾（預設 data/今天）")
    ap.add_argument("--date", default=None, help="輸出資料夾用的日期 YYYYMMDD（預設今天）")
    args = ap.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    date = args.date or datetime.date.today().strftime("%Y%m%d")
    out_dir = args.out or os.path.join(root, "data", date)
    os.makedirs(out_dir, exist_ok=True)

    print(f"BSR 抓取 {len(args.codes)} 檔 → {out_dir}", flush=True)
    ok = 0; failed = []
    for code in args.codes:
        try:
            recs = fetch_records(code)
        except Exception as e:
            print(f"  {code}: 例外 {type(e).__name__}", flush=True)
            failed.append(code); continue
        if recs is _NO_DATA:
            print(f"  {code}: 當日無資料（未交易或尚未產表）", flush=True)
            failed.append(code); continue
        if not recs:
            print(f"  {code}: 失敗（重試耗盡／被限流）", flush=True)
            failed.append(code); continue
        buy = sum(r["買進股數"] for r in recs)
        sell = sum(r["賣出股數"] for r in recs)
        # 完整資料 Σ買≈Σ賣（差異來自零股/盤後四捨五入）；只讀半套會差到 ~0.6%。
        balanced = abs(buy - sell) <= max(50, buy * 0.001)
        save_csv(recs, os.path.join(out_dir, f"{code}_bsr.csv"))
        flag = "OK" if balanced else "[!] 買賣不平衡(資料可能不完整)"
        print(f"  {code}: {len(recs)} 筆，Σ買={buy:,} Σ賣={sell:,} {flag}", flush=True)
        ok += 1
        time.sleep(1.5)   # 對伺服器客氣一點
    print(f"完成 {ok}/{len(args.codes)}" + (f"；失敗：{','.join(failed)}" if failed else ""), flush=True)
    sys.exit(0 if ok == len(args.codes) else 1)


if __name__ == "__main__":
    main()
