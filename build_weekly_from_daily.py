#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_weekly_from_daily.py — 從「每日」網站資料彙總出「週報」(週五~下週四)。

週的定義為**週五～下週四**，對齊集保戶股權分散表的每週統計區間(2015 後每週公布，
官方資料區間為週五到下週四)，方便與股權分散資料對比。本工具直接彙總
site/data/<YYYYMMDD>/<code>.json 的分點資料，產出與原週報相同結構的
site/data/weekly/<wkey>/<code>.json 與 <code>_vol.json。收盤價取自 tw_volume.db。
不滿一週(1~4 天)就先產部分週，之後每天再跑會自動補到週四完整。

用法：
    python build_weekly_from_daily.py --check 20260529-0604   # 驗證：重算舊週與夥伴原檔比對
    python build_weekly_from_daily.py 20260601-0605            # 產生該週（寫入 site/data/weekly/）
之後請接著跑 build.py 產生 .js 包裝並更新 index。
"""
import os, re, json, glob, sqlite3, sys, datetime, argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "site", "data")
DB_PATH = os.path.join(ROOT, "tw_volume.db")


def load_data_file(path):
    """讀 .js(__DATAREG 包裝) 或 .json，回傳 dict。"""
    with open(path, encoding="utf-8") as f:
        t = f.read()
    return json.loads(t[t.index("{"):t.rindex("}") + 1])


def strip_cn(s):
    return re.sub(r"[^一-龥]", "", str(s))


def _intify(x):
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


def week_dates(wkey):
    """wkey 20260601-0605 → 該日曆範圍內、且 site/data/ 有資料夾的交易日 [YYYYMMDD,...]。"""
    start = wkey.split("-")[0]
    end_raw = wkey.split("-")[1]
    end = (start[:4] + end_raw) if len(end_raw) == 4 else end_raw
    d0 = datetime.datetime.strptime(start, "%Y%m%d").date()
    d1 = datetime.datetime.strptime(end, "%Y%m%d").date()
    out = []
    d = d0
    while d <= d1:
        ymd = d.strftime("%Y%m%d")
        if os.path.isdir(os.path.join(OUT_DIR, ymd)):
            out.append(ymd)
        d += datetime.timedelta(days=1)
    return out


def stock_codes_in(dates):
    """這些日子裡出現過的 4 碼個股代號（聯集）。"""
    codes = set()
    for ymd in dates:
        for jp in glob.glob(os.path.join(OUT_DIR, ymd, "*.js")):
            base = os.path.basename(jp)[:-3]
            if re.fullmatch(r"\d{4}", base):
                codes.add(base)
    return sorted(codes)


def get_close(con, code, ymd):
    iso = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
    r = con.execute("SELECT close_price FROM daily_volume WHERE stock_id=? AND date=?",
                    (code, iso)).fetchone()
    return r[0] if r else None


def build_main(code, name, daily):
    """週報主檔 buy_top/sell_top：跨整週、依券商(去非中文)彙總 broker_detail。"""
    agg = {}
    for d in daily:
        for r in d.get("broker_detail", []):
            b = strip_cn(r.get("券商", "")) or r.get("券商", "")
            px = r.get("股價", 0) or 0
            bq_, sq_ = r.get("買進股數", 0) or 0, r.get("賣出股數", 0) or 0
            a = agg.setdefault(b, {"bq": 0, "bv": 0.0, "sq": 0, "sv": 0.0})
            a["bq"] += bq_; a["bv"] += px * bq_
            a["sq"] += sq_; a["sv"] += px * sq_
    brokers = []
    for b, a in agg.items():
        brokers.append({
            "券商": b,
            "buy_total_qty": _intify(a["bq"] / 1000), "buy_total_value": _intify(a["bv"]),
            "buy_avg_price": (a["bv"] / a["bq"]) if a["bq"] else 0,
            "sell_total_qty": _intify(a["sq"] / 1000), "sell_total_value": _intify(a["sv"]),
            "sell_avg_price": (a["sv"] / a["sq"]) if a["sq"] else 0,
            "buy_sell_diff": _intify((a["bq"] - a["sq"]) / 1000),
        })
    buy_top = sorted(brokers, key=lambda x: x["buy_total_qty"], reverse=True)[:20]
    sell_top = sorted(brokers, key=lambda x: x["sell_total_qty"], reverse=True)[:20]
    return {"code": code, "name": name, "buy_top": buy_top, "sell_top": sell_top}


def build_vol(code, name, dates, daily_by_date, con):
    """大量與均價：每日摘要 + 每日前10明細。"""
    daily_summary, top10_detail = [], []
    for ymd in dates:
        d = daily_by_date[ymd]
        iso = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
        pv = d.get("price_volume", [])
        bt, st = d.get("buy_top", []), d.get("sell_top", [])
        rec = {"date": iso}
        if pv:
            big = max(pv, key=lambda r: r.get("買進股數", 0) or 0)  # 大量 = 買進量最大的價位
            rec.update({
                "price": big.get("股價"),
                "buy_qty": big.get("買進股數", 0), "sell_qty": big.get("賣出股數", 0),
                "buy_cnt": big.get("買進家數", 0), "sell_cnt": big.get("賣出家數", 0),
                "max_buy_qty": big.get("最高買進股數", 0), "max_sell_qty": big.get("最高賣出股數", 0),
            })
        rec["close"] = get_close(con, code, ymd)
        b10, s10 = bt[:10], st[:10]
        rec["top10_buy_qty"] = sum(r.get("buy_total_qty", 0) or 0 for r in b10)
        rec["top10_buy_avg"] = (sum(r.get("buy_avg_price", 0) or 0 for r in b10) / len(b10)) if b10 else 0
        rec["top10_sell_qty"] = sum(r.get("sell_total_qty", 0) or 0 for r in s10)
        rec["top10_sell_avg"] = (sum(r.get("sell_avg_price", 0) or 0 for r in s10) / len(s10)) if s10 else 0
        daily_summary.append(rec)
        n = max(len(b10), len(s10))
        brokers = []
        for i in range(n):
            b = b10[i] if i < len(b10) else {}
            s = s10[i] if i < len(s10) else {}
            brokers.append({
                "buy_qty": b.get("buy_total_qty", 0), "buy_avg": b.get("buy_avg_price", 0),
                "sell_qty": s.get("sell_total_qty", 0), "sell_avg": s.get("sell_avg_price", 0),
            })
        top10_detail.append({"date": iso, "brokers": brokers})
    return {"code": code, "name": name, "daily_summary": daily_summary, "top10_detail": top10_detail}


def build_week(wkey, con):
    dates = week_dates(wkey)
    if not dates:
        sys.exit(f"{wkey}: 範圍內找不到任何有資料的交易日")
    codes = stock_codes_in(dates)
    print(f"{wkey} → 交易日 {dates}；個股 {codes}", flush=True)
    out = {}
    for code in codes:
        daily_by_date = {}
        for ymd in dates:
            p = os.path.join(OUT_DIR, ymd, f"{code}.js")
            if os.path.exists(p):
                daily_by_date[ymd] = load_data_file(p)
        avail = [ymd for ymd in dates if ymd in daily_by_date]
        name = next((daily_by_date[y].get("name", "") for y in avail if daily_by_date[y].get("name")), "")
        daily_list = [daily_by_date[y] for y in avail]
        main = build_main(code, name, daily_list)
        vol = build_vol(code, name, avail, daily_by_date, con)
        out[code] = (main, vol)
    return out


# ---------- 驗證 ----------
def _close(a, b, tol=0.01):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    return a == b


def deep_diff(path, a, b, diffs):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            deep_diff(f"{path}.{k}", a.get(k), b.get(k), diffs)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append(f"{path}: 長度 {len(a)} vs {len(b)}")
        for i in range(min(len(a), len(b))):
            deep_diff(f"{path}[{i}]", a[i], b[i], diffs)
    elif not _close(a, b):
        diffs.append(f"{path}: {a!r} vs {b!r}")


def check(wkey, con):
    built = build_week(wkey, con)
    total = 0
    for code, (main, vol) in built.items():
        for kind, got in (("", main), ("_vol", vol)):
            exp_path = os.path.join(OUT_DIR, "weekly", wkey, f"{code}{kind}.js")
            if not os.path.exists(exp_path):
                print(f"  [{code}{kind}] 找不到原檔，略過"); continue
            exp = load_data_file(exp_path)
            diffs = []
            deep_diff(f"{code}{kind}", got, exp, diffs)
            total += len(diffs)
            tag = "✓" if not diffs else f"✗ {len(diffs)} 處不同"
            print(f"  [{code}{kind}] {tag}")
            for dd in diffs[:8]:
                print(f"      {dd}")
    print(f"\n驗證結果：{'完全一致 ✓' if total == 0 else f'共 {total} 處差異'}")
    return total == 0


def generate(wkey, con):
    built = build_week(wkey, con)
    outdir = os.path.join(OUT_DIR, "weekly", wkey)
    os.makedirs(outdir, exist_ok=True)
    for code, (main, vol) in built.items():
        with open(os.path.join(outdir, f"{code}.json"), "w", encoding="utf-8") as f:
            json.dump(main, f, ensure_ascii=False, separators=(",", ":"))
        with open(os.path.join(outdir, f"{code}_vol.json"), "w", encoding="utf-8") as f:
            json.dump(vol, f, ensure_ascii=False, separators=(",", ":"))
    print(f"已寫入 {outdir}（{len(built)} 檔個股，每檔 .json + _vol.json）")
    print("接著請跑：python build.py  （產生 .js 包裝並更新 index 的 weekly_dates）")


def _latest_daily_date():
    cands = [os.path.basename(d) for d in glob.glob(os.path.join(OUT_DIR, "*"))
             if os.path.isdir(d) and re.fullmatch(r"\d{8}", os.path.basename(d))]
    return max(cands) if cands else None


def _anchor_friday(d):
    """回傳 date d 所屬『週五~下週四』週的錨點（該週的星期五）。
    對齊集保戶股權分散表的每週統計區間（週五到下週四）。"""
    wd = d.weekday()                 # Mon=0 ... Fri=4, Sat=5, Sun=6
    if wd == 4:                      # 星期五：本身即錨點
        return d
    if wd < 4:                       # 週一~週四：往回找上一個星期五
        return d - datetime.timedelta(days=wd + 3)
    return d - datetime.timedelta(days=wd - 4)   # 週六/日：回到本週五


def current_week_wkey():
    """以最新交易日所在的『週五~下週四』週，回傳 (wkey, 該週錨點星期五)。
    wkey = 該週「最早~最晚」有資料的交易日（不滿一週就是部分範圍，結尾用目前最後一天）。"""
    latest = _latest_daily_date()
    if not latest:
        sys.exit("site/data 下找不到任何每日資料夾")
    dt = datetime.datetime.strptime(latest, "%Y%m%d").date()
    fri = _anchor_friday(dt)
    covered = []
    d = fri
    while d <= dt:                   # 錨點星期五 → 最新交易日
        ymd = d.strftime("%Y%m%d")
        if os.path.isdir(os.path.join(OUT_DIR, ymd)):
            covered.append(ymd)
        d += datetime.timedelta(days=1)
    if not covered:
        sys.exit(f"本週({fri}~{dt})無任何日資料")
    wkey = covered[0] + "-" + covered[-1][4:]   # YYYYMMDD-MMDD
    return wkey, fri


def remove_stale_same_week(anchor_fri, keep_wkey):
    """刪掉 site/data/weekly 下、屬於同一週(同錨點星期五)但 wkey 不同的舊(部分)桶，
    確保每週只留一個桶（避免每天滾動產生重複部分桶）。"""
    wroot = os.path.join(OUT_DIR, "weekly")
    if not os.path.isdir(wroot):
        return
    import shutil
    for d in glob.glob(os.path.join(wroot, "*")):
        wk = os.path.basename(d)
        if not os.path.isdir(d) or not re.match(r"\d{8}-\d{4,8}$", wk) or wk == keep_wkey:
            continue
        try:
            sdt = datetime.datetime.strptime(wk.split("-")[0], "%Y%m%d").date()
            if _anchor_friday(sdt) == anchor_fri:
                shutil.rmtree(d)
                print(f"  移除同週舊桶：{wk}", flush=True)
        except Exception:
            pass


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("wkey", nargs="?", help="週鍵，如 20260601-0605（用 --current 時可省略）")
    ap.add_argument("--check", action="store_true", help="驗證模式：與現有同 wkey 原檔逐欄比對，不寫檔")
    ap.add_argument("--current", action="store_true",
                    help="自動產生『最新交易日所在的當前週』(不滿一週就部分)，並清掉同週舊桶")
    args = ap.parse_args()
    con = sqlite3.connect(DB_PATH)
    try:
        if args.current:
            wkey, anchor = current_week_wkey()
            print(f"當前週 wkey = {wkey}（錨點星期五 {anchor}）", flush=True)
            remove_stale_same_week(anchor, wkey)
            generate(wkey, con)
        elif not args.wkey:
            ap.error("請提供 wkey，或用 --current")
        elif args.check:
            sys.exit(0 if check(args.wkey, con) else 1)
        else:
            generate(args.wkey, con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
