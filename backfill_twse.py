#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_twse.py — 補抓 tw_volume.db 裡缺漏的「上市(TWSE)」每日量價。

背景：volume_system.py --init 連續抓 150 天時，TWSE 的 MI_INDEX 端點會限流，
回非 OK 的 JSON，而 fetch_twse_day() 對非 OK 是「靜默回空」→ 結果整個 DB 只存了
上櫃(TPEX)、上市(TWSE) 一筆都沒有，導致放量訊號全是上櫃。
（fetch_history 又是用「日期」判斷已抓，重跑 --init 會整天跳過，補不回來。）

本工具：對 DB 內每個已存在的交易日，若該日尚無 TWSE 資料，就呼叫
volume_system.fetch_twse_day() 補抓；遇到空（限流）就退避重試，並放慢節奏。
補完後請再跑：python volume_system.py --update  以重算最新日訊號並匯出 Excel。
"""
import sys, time
import volume_system as vs

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def robust_fetch_twse(raw, tries=6):
    """呼叫 fetch_twse_day；空就退避重試（限流多半隔幾秒就好）。"""
    for attempt in range(tries):
        df = vs.fetch_twse_day(raw)
        if df is not None and not df.empty:
            return df
        wait = 2 * (attempt + 1)
        print(f"      非OK/空，等 {wait}s 重試（{attempt + 1}/{tries}）", flush=True)
        time.sleep(wait)
    return None


def main():
    con = vs.init_db()
    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM daily_volume ORDER BY date").fetchall()]
    print(f"DB 內共 {len(dates)} 個交易日，逐日檢查/補抓 TWSE…", flush=True)

    added_total = 0
    skipped = 0
    failed = []
    for i, d in enumerate(dates):
        # 用 daily_volume 自己的 market 欄位判斷（不可 JOIN stock_info：
        # save_stock_names 的 INSERT OR REPLACE 可能把跨市場重複代號翻成 TWSE，
        # 害 JOIN 誤判某些日「已有 TWSE」而錯誤跳過）。
        have = con.execute(
            "SELECT COUNT(*) FROM daily_volume WHERE date=? AND market='TWSE'",
            (d,)).fetchone()[0]
        if have > 0:
            skipped += 1
            continue
        raw = d.replace("-", "")
        df = robust_fetch_twse(raw)
        if df is None or df.empty:
            print(f"[{i+1}/{len(dates)}] {d} TWSE 補抓失敗，跳過", flush=True)
            failed.append(d)
            continue
        df = df[df["volume"] > 0]
        # 先存名稱（save_stock_names 會 upsert stock_info）
        name_df = df[["stock_id", "stock_name", "market"]].copy()
        name_df["updated_date"] = d
        vs.save_stock_names(con, name_df)
        ins = df.drop(columns=["stock_name"])
        existing_ids = {r[0] for r in con.execute(
            "SELECT stock_id FROM daily_volume WHERE date=?", (d,)).fetchall()}
        ins = ins[~ins["stock_id"].isin(existing_ids)]
        if not ins.empty:
            ins.to_sql("daily_volume", con, if_exists="append", index=False)
            con.commit()
            vs.fix_zero_change_pct(con, d)   # 除息/除權漲跌幅補正
            added_total += len(ins)
        print(f"[{i+1}/{len(dates)}] {d} +{len(ins)} TWSE 筆", flush=True)
        time.sleep(1.3)   # 對 TWSE 客氣，降低再次限流機率

    print(f"\nTWSE 補抓完成：新增 {added_total:,} 筆；"
          f"原已有 TWSE 而跳過 {skipped} 日"
          + (f"；失敗 {len(failed)} 日：{','.join(failed)}" if failed else ""), flush=True)
    con.close()
    print("接著請執行：python volume_system.py --update", flush=True)


if __name__ == "__main__":
    main()
