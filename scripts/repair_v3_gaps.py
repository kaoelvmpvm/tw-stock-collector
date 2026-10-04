#!/usr/bin/env python3
"""
Repair known V3 backtest data gaps for 2026-04-01..2026-10-02.

This script:
1. Removes files accidentally collected on confirmed market-closure dates.
2. Re-fetches only the known partial price dates until both TWSE and TPEx are present.
3. Re-fetches only the known partial institutional dates until both TWSE and TPEx are present.
4. Writes an audit manifest and exits non-zero if any repair remains incomplete.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from services.common.collectors import PriceCollector, InstitutionalCollector
from services.common.utils.file_helper import get_file_path, save_json

PRICE_REPAIR_DATES = [
    "2026-04-14",
    "2026-05-04",
    "2026-05-14",
    "2026-06-09",
    "2026-06-15",
    "2026-06-26",
    "2026-07-13",
    "2026-07-17",
    "2026-07-23",
    "2026-08-12",
    "2026-08-21",
    "2026-09-07",
    "2026-09-10",
    "2026-10-01",
]

INSTITUTIONAL_REPAIR_DATES = [
    "2026-04-07",
    "2026-04-17",
    "2026-06-04",
    "2026-08-05",
    "2026-08-17",
    "2026-08-27",
    "2026-08-31",
    "2026-09-16",
    "2026-09-23",
]

# Confirmed TWSE/TPEx full-market closure dates inside the backtest interval.
CLOSED_DATES = [
    "2026-04-03",
    "2026-04-06",
    "2026-05-01",
    "2026-06-19",
    "2026-07-10",
    "2026-09-25",
    "2026-09-28",
]

DATA_TYPES = ["price", "institutional", "margin", "lending"]
MAX_ATTEMPTS = 6

# Loose lower bounds: designed to reject one-market-only files without depending
# on an exact number of listed companies.
PRICE_MIN_TWSE = 900
PRICE_MIN_TPEX = 700
INST_MIN_TWSE = 900
INST_MIN_TPEX = 700


def companion_paths(data_type: str, date: str):
    base = Path(get_file_path(data_type, date))
    yield base
    yield Path(str(base) + ".md5")
    yield base.with_name(f"{date}-report.md")


def remove_closed_date_artifacts():
    removed = []
    for date in CLOSED_DATES:
        for data_type in DATA_TYPES:
            for path in companion_paths(data_type, date):
                if path.exists():
                    path.unlink()
                    removed.append(str(path))
                    print(f"[REMOVE] closed market date: {path}")
    return removed


def remove_stale_validation(data_type: str, date: str):
    base = Path(get_file_path(data_type, date))
    for path in [Path(str(base) + ".md5"), base.with_name(f"{date}-report.md")]:
        if path.exists():
            path.unlink()


def market_counts(data):
    rows = (data or {}).get("data") or []
    twse = sum(1 for row in rows if str(row.get("type", "")).lower() == "twse")
    tpex = sum(1 for row in rows if str(row.get("type", "")).lower() == "tpex")
    return twse, tpex, len(rows)


def repair_price(date: str):
    errors = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            data = PriceCollector(date).collect()
            twse, tpex, total = market_counts(data)
            print(f"[PRICE] {date} attempt={attempt} twse={twse} tpex={tpex} total={total}")
            if twse >= PRICE_MIN_TWSE and tpex >= PRICE_MIN_TPEX:
                meta = data.setdefault("metadata", {})
                meta["repair"] = {
                    "reason": "V3 gap repair: one exchange missing in original backfill",
                    "repaired_at": datetime.now().isoformat(timespec="seconds"),
                    "attempt": attempt,
                }
                save_json(data, get_file_path("price", date))
                remove_stale_validation("price", date)
                return {"date": date, "twse": twse, "tpex": tpex, "total": total, "attempt": attempt}
            errors.append(f"attempt {attempt}: incomplete counts twse={twse} tpex={tpex}")
        except Exception as exc:
            errors.append(f"attempt {attempt}: {exc}")
            print(f"[WARN] price {date}: {exc}")
        time.sleep(min(12, attempt * 2))
    raise RuntimeError(f"price {date} repair failed: {'; '.join(errors)}")


def repair_institutional(date: str):
    errors = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            data = InstitutionalCollector(date).collect()
            twse, tpex, total = market_counts(data)
            print(f"[INST] {date} attempt={attempt} twse={twse} tpex={tpex} total={total}")
            if twse >= INST_MIN_TWSE and tpex >= INST_MIN_TPEX:
                meta = data.setdefault("metadata", {})
                meta["twse_count"] = twse
                meta["tpex_count"] = tpex
                meta["repair"] = {
                    "reason": "V3 gap repair: TPEx institutional response incomplete in original backfill",
                    "repaired_at": datetime.now().isoformat(timespec="seconds"),
                    "attempt": attempt,
                }
                save_json(data, get_file_path("institutional", date))
                remove_stale_validation("institutional", date)
                return {"date": date, "twse": twse, "tpex": tpex, "total": total, "attempt": attempt}
            errors.append(f"attempt {attempt}: incomplete counts twse={twse} tpex={tpex}")
        except Exception as exc:
            errors.append(f"attempt {attempt}: {exc}")
            print(f"[WARN] institutional {date}: {exc}")
        time.sleep(min(12, attempt * 2))
    raise RuntimeError(f"institutional {date} repair failed: {'; '.join(errors)}")


def main():
    audit = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "V3 backtest data gap repair 2026-04-01..2026-10-02",
        "closed_dates": CLOSED_DATES,
        "removed_closed_date_artifacts": remove_closed_date_artifacts(),
        "price": [],
        "institutional": [],
        "failures": [],
    }

    for date in PRICE_REPAIR_DATES:
        try:
            audit["price"].append(repair_price(date))
        except Exception as exc:
            print(f"[ERROR] {exc}")
            audit["failures"].append({"type": "price", "date": date, "error": str(exc)})

    for date in INSTITUTIONAL_REPAIR_DATES:
        try:
            audit["institutional"].append(repair_institutional(date))
        except Exception as exc:
            print(f"[ERROR] {exc}")
            audit["failures"].append({"type": "institutional", "date": date, "error": str(exc)})

    manifest = Path("data/v3_repair_20260401_20261002.json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== REPAIR SUMMARY ===")
    print(f"price repaired={len(audit['price'])}/{len(PRICE_REPAIR_DATES)}")
    print(f"institutional repaired={len(audit['institutional'])}/{len(INSTITUTIONAL_REPAIR_DATES)}")
    print(f"closed-date artifacts removed={len(audit['removed_closed_date_artifacts'])}")
    print(f"failures={len(audit['failures'])}")

    if audit["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
