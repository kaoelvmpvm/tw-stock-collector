#!/usr/bin/env python3
"""
V3 final integrity audit for the 2026-04-01..2026-10-02 backtest dataset.

The audit is intentionally read-only for raw data. It checks:
- expected trading-day coverage and stray non-trading-day files
- JSON structure, metadata/date/count consistency, duplicate stock ids
- TWSE/TPEx market coverage for price / institutional / margin
- basic OHLC/volume sanity
- semantic usefulness of institutional standard fields
- suspicious identical consecutive trading-day snapshots
- cross-type date alignment

Outputs:
  data/v3_integrity_report_20260401_20261002.json
  data/v3_integrity_report_20260401_20261002.md

Exit code 0 = PASS (no critical findings)
Exit code 1 = FAIL (one or more critical findings)
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HOLIDAYS_2026 = {
    "2026-01-01",
    "2026-02-12","2026-02-13","2026-02-16","2026-02-17","2026-02-18","2026-02-19","2026-02-20",
    "2026-02-27",
    "2026-04-03","2026-04-06",
    "2026-05-01",
    "2026-06-19",
    "2026-07-10",
    "2026-09-25","2026-09-28",
    "2026-10-09","2026-10-26",
    "2026-12-25",
}

def is_trading_day(date_str: str) -> bool:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return d.weekday() < 5 and date_str not in HOLIDAYS_2026


START = "2026-04-01"
END = "2026-10-02"
TYPES = ("price", "institutional", "margin", "lending")
RAW_ROOT = Path("data/raw")
REPORT_JSON = Path("data/v3_integrity_report_20260401_20261002.json")
REPORT_MD = Path("data/v3_integrity_report_20260401_20261002.md")

MARKET_MINIMUMS = {
    "price": {"twse": 900, "tpex": 700, "total": 1600},
    "institutional": {"twse": 900, "tpex": 700, "total": 1600},
    "margin": {"twse": 900, "tpex": 700, "total": 1600},
    "lending": {"total": 800},
}

SIGNATURE_FIELDS = {
    "price": ("stock_id", "open", "high", "low", "close", "volume"),
    "institutional": ("stock_id", "foreign_net", "trust_net", "dealer_net", "total_net"),
    "margin": ("stock_id", "margin_balance", "short_balance"),
    "lending": ("stock_id", "prev_balance", "daily_sell", "daily_return", "lending_balance"),
}


def daterange(start: str, end: str):
    cur = datetime.strptime(start, "%Y-%m-%d").date()
    stop = datetime.strptime(end, "%Y-%m-%d").date()
    while cur <= stop:
        yield cur.strftime("%Y-%m-%d")
        cur += timedelta(days=1)


def path_for(data_type: str, date: str) -> Path:
    return RAW_ROOT / data_type / date[:4] / date[5:7] / f"{date}.json"


def add_issue(report, severity, code, message, **detail):
    item = {"severity": severity, "code": code, "message": message}
    if detail:
        item["detail"] = detail
    report["issues"].append(item)
    report["summary"][severity] += 1


def market_counts(rows):
    counts = defaultdict(int)
    for row in rows:
        counts[str(row.get("type", "")).lower()] += 1
    return dict(counts)


def normalized_signature(data_type: str, rows) -> str:
    fields = SIGNATURE_FIELDS[data_type]
    normalized = []
    for row in rows:
        normalized.append(tuple(row.get(k) for k in fields))
    normalized.sort(key=lambda x: str(x[0]))
    blob = json.dumps(normalized, ensure_ascii=False, sort_keys=False, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def nonzero(value):
    try:
        return float(value) != 0.0
    except Exception:
        return False


def main():
    all_dates = list(daterange(START, END))
    expected = [d for d in all_dates if is_trading_day(d)]
    closed = [d for d in all_dates if not is_trading_day(d)]

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {"start": START, "end": END},
        "expected_trading_days": expected,
        "expected_trading_day_count": len(expected),
        "non_trading_day_count": len(closed),
        "summary": {"critical": 0, "warning": 0, "info": 0},
        "type_stats": {},
        "issues": [],
        "overall": "PASS",
    }

    type_dates = {}
    signatures = {t: {} for t in TYPES}
    daily_counts = {t: {} for t in TYPES}

    for data_type in TYPES:
        existing = []
        missing = []
        stray = []
        parse_failures = []
        type_stats = {
            "expected_files": len(expected),
            "existing_expected_files": 0,
            "missing_files": [],
            "stray_non_trading_files": [],
            "record_counts": {},
            "market_counts": {},
        }

        for date in all_dates:
            p = path_for(data_type, date)
            if p.exists():
                if date in expected:
                    existing.append(date)
                else:
                    stray.append(date)

        for date in expected:
            p = path_for(data_type, date)
            if not p.exists():
                missing.append(date)
                add_issue(
                    report, "critical", "MISSING_FILE",
                    f"{data_type} 缺少預期交易日檔案 {date}",
                    data_type=data_type, date=date, path=str(p)
                )
                continue

            try:
                with p.open("r", encoding="utf-8") as fh:
                    obj = json.load(fh)
            except Exception as exc:
                parse_failures.append(date)
                add_issue(
                    report, "critical", "INVALID_JSON",
                    f"{data_type} {date} JSON 無法解析",
                    data_type=data_type, date=date, error=str(exc)
                )
                continue

            meta = obj.get("metadata") if isinstance(obj, dict) else None
            rows = obj.get("data") if isinstance(obj, dict) else None
            if not isinstance(meta, dict) or not isinstance(rows, list):
                add_issue(
                    report, "critical", "BAD_STRUCTURE",
                    f"{data_type} {date} 缺少 metadata/data 標準結構",
                    data_type=data_type, date=date
                )
                continue

            if meta.get("date") != date:
                add_issue(
                    report, "critical", "METADATA_DATE_MISMATCH",
                    f"{data_type} {date} metadata.date 不一致",
                    data_type=data_type, date=date, metadata_date=meta.get("date")
                )

            total_count = meta.get("total_count")
            if total_count is not None:
                try:
                    if int(total_count) != len(rows):
                        add_issue(
                            report, "critical", "TOTAL_COUNT_MISMATCH",
                            f"{data_type} {date} metadata.total_count 與實際筆數不一致",
                            data_type=data_type, date=date,
                            metadata_total=total_count, actual_total=len(rows)
                        )
                except Exception:
                    add_issue(
                        report, "warning", "BAD_TOTAL_COUNT_TYPE",
                        f"{data_type} {date} metadata.total_count 不是有效整數",
                        data_type=data_type, date=date, metadata_total=total_count
                    )

            ids = [str(r.get("stock_id", "")) for r in rows if isinstance(r, dict)]
            missing_id = sum(1 for x in ids if not x)
            if missing_id:
                add_issue(
                    report, "critical", "MISSING_STOCK_ID",
                    f"{data_type} {date} 有 {missing_id} 筆缺少 stock_id",
                    data_type=data_type, date=date, count=missing_id
                )

            duplicates = len(ids) - len(set(ids))
            if duplicates:
                add_issue(
                    report, "critical", "DUPLICATE_STOCK_ID",
                    f"{data_type} {date} 有重複 stock_id",
                    data_type=data_type, date=date, duplicate_count=duplicates
                )

            bad_record_dates = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_date = row.get("date")
                if row_date is not None and row_date != date:
                    bad_record_dates += 1
            if bad_record_dates:
                add_issue(
                    report, "critical", "ROW_DATE_MISMATCH",
                    f"{data_type} {date} 有 {bad_record_dates} 筆 row.date 不一致",
                    data_type=data_type, date=date, count=bad_record_dates
                )

            counts = market_counts(rows)
            daily_counts[data_type][date] = len(rows)
            type_stats["record_counts"][date] = len(rows)
            type_stats["market_counts"][date] = counts

            mins = MARKET_MINIMUMS[data_type]
            if len(rows) < mins["total"]:
                add_issue(
                    report, "critical", "LOW_TOTAL_COVERAGE",
                    f"{data_type} {date} 資料筆數過低",
                    data_type=data_type, date=date, actual=len(rows), minimum=mins["total"]
                )

            for market in ("twse", "tpex"):
                if market in mins:
                    actual = counts.get(market, 0)
                    if actual < mins[market]:
                        add_issue(
                            report, "critical", "LOW_MARKET_COVERAGE",
                            f"{data_type} {date} {market.upper()} 覆蓋不足",
                            data_type=data_type, date=date, market=market,
                            actual=actual, minimum=mins[market]
                        )

            if data_type == "price":
                invalid_ohlc = 0
                negative_volume = 0
                for row in rows:
                    try:
                        o = float(row.get("open", 0) or 0)
                        h = float(row.get("high", 0) or 0)
                        lo = float(row.get("low", 0) or 0)
                        c = float(row.get("close", 0) or 0)
                        if h < lo or (h > 0 and max(o, c) > h) or (lo > 0 and min(o, c) < lo):
                            invalid_ohlc += 1
                    except Exception:
                        invalid_ohlc += 1
                    try:
                        if float(row.get("volume", 0) or 0) < 0:
                            negative_volume += 1
                    except Exception:
                        negative_volume += 1
                if invalid_ohlc:
                    sev = "critical" if invalid_ohlc > max(3, len(rows) * 0.002) else "warning"
                    add_issue(
                        report, sev, "INVALID_OHLC",
                        f"price {date} 有 {invalid_ohlc} 筆 OHLC 邏輯異常",
                        date=date, count=invalid_ohlc, total=len(rows)
                    )
                if negative_volume:
                    add_issue(
                        report, "critical", "NEGATIVE_VOLUME",
                        f"price {date} 有負成交量",
                        date=date, count=negative_volume
                    )

            if data_type == "institutional":
                # Standardized signal fields must carry actual TPEx information.
                tpex_rows = [r for r in rows if str(r.get("type", "")).lower() == "tpex"]
                if tpex_rows:
                    signal_fields = ("foreign_net", "trust_net", "dealer_net")
                    nonzero_rows = sum(
                        1 for row in tpex_rows
                        if any(nonzero(row.get(field)) for field in signal_fields)
                    )
                    ratio = nonzero_rows / len(tpex_rows)
                    if nonzero_rows == 0:
                        add_issue(
                            report, "critical", "TPEX_INSTITUTIONAL_STANDARD_FIELDS_ALL_ZERO",
                            f"institutional {date} TPEx 標準法人欄位全部為 0",
                            date=date, tpex_rows=len(tpex_rows),
                            fields=list(signal_fields)
                        )
                    elif ratio < 0.05:
                        add_issue(
                            report, "warning", "TPEX_INSTITUTIONAL_LOW_SIGNAL_DENSITY",
                            f"institutional {date} TPEx 標準法人欄位非零比例異常偏低",
                            date=date, tpex_rows=len(tpex_rows),
                            nonzero_rows=nonzero_rows, ratio=ratio
                        )

            signatures[data_type][date] = normalized_signature(data_type, rows)

        for date in stray:
            add_issue(
                report, "critical", "STRAY_NON_TRADING_FILE",
                f"{data_type} 在非交易日 {date} 仍存在 JSON",
                data_type=data_type, date=date, path=str(path_for(data_type, date))
            )

        type_stats["existing_expected_files"] = len(existing)
        type_stats["missing_files"] = missing
        type_stats["stray_non_trading_files"] = stray
        type_stats["parse_failures"] = parse_failures

        counts_list = list(daily_counts[data_type].values())
        if counts_list:
            type_stats["count_distribution"] = {
                "min": min(counts_list),
                "max": max(counts_list),
                "median": statistics.median(counts_list),
                "mean": round(statistics.mean(counts_list), 2),
            }
        report["type_stats"][data_type] = type_stats
        type_dates[data_type] = set(existing)

    # Date alignment across all four data types.
    for date in expected:
        have = [t for t in TYPES if date in type_dates.get(t, set())]
        if len(have) != len(TYPES):
            add_issue(
                report, "critical", "CROSS_TYPE_DATE_MISALIGNMENT",
                f"{date} 四種資料日期未對齊",
                date=date, present=have, missing=[t for t in TYPES if t not in have]
            )

    # Adjacent expected trading days should not have byte-equivalent market snapshots
    # once the date field is excluded from signatures.
    for data_type in TYPES:
        prev_date = None
        prev_sig = None
        for date in expected:
            sig = signatures[data_type].get(date)
            if sig and prev_sig and sig == prev_sig:
                add_issue(
                    report, "warning", "IDENTICAL_CONSECUTIVE_SNAPSHOT",
                    f"{data_type} {prev_date} 與 {date} 的核心資料完全相同",
                    data_type=data_type, previous_date=prev_date, date=date
                )
            if sig:
                prev_date, prev_sig = date, sig

    if report["summary"]["critical"] > 0:
        report["overall"] = "FAIL"
    elif report["summary"]["warning"] > 0:
        report["overall"] = "PASS_WITH_WARNINGS"

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = []
    md.append("# V3 回測資料最終完整性檢查")
    md.append("")
    md.append(f"- 範圍：{START} ～ {END}")
    md.append(f"- 預期交易日：{len(expected)}")
    md.append(f"- 結果：**{report['overall']}**")
    md.append(f"- Critical：{report['summary']['critical']}")
    md.append(f"- Warning：{report['summary']['warning']}")
    md.append("")
    md.append("## 各類型檔案覆蓋")
    md.append("")
    md.append("| 類型 | 預期 | 存在 | 缺檔 | 非交易日誤檔 |")
    md.append("|---|---:|---:|---:|---:|")
    for t in TYPES:
        st = report["type_stats"][t]
        md.append(
            f"| {t} | {st['expected_files']} | {st['existing_expected_files']} | "
            f"{len(st['missing_files'])} | {len(st['stray_non_trading_files'])} |"
        )
    md.append("")
    md.append("## 問題摘要")
    md.append("")
    if not report["issues"]:
        md.append("未發現問題。")
    else:
        for issue in report["issues"][:300]:
            md.append(f"- **{issue['severity'].upper()} / {issue['code']}**：{issue['message']}")
        if len(report["issues"]) > 300:
            md.append(f"- 其餘 {len(report['issues']) - 300} 項詳見 JSON 報告。")
    REPORT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print("=== V3 FINAL INTEGRITY AUDIT ===")
    print(f"expected_trading_days={len(expected)}")
    for t in TYPES:
        st = report["type_stats"][t]
        print(
            f"{t}: files={st['existing_expected_files']}/{st['expected_files']} "
            f"missing={len(st['missing_files'])} stray={len(st['stray_non_trading_files'])}"
        )
        if "count_distribution" in st:
            print(f"  counts={st['count_distribution']}")
    print(f"critical={report['summary']['critical']}")
    print(f"warning={report['summary']['warning']}")
    print(f"overall={report['overall']}")
    print(f"report={REPORT_JSON}")

    raise SystemExit(1 if report["summary"]["critical"] else 0)


if __name__ == "__main__":
    main()
