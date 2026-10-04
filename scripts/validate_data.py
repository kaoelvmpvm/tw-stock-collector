#!/usr/bin/env python3
"""
資料驗證腳本

驗證收集的資料並生成驗證報告
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# 添加專案根目錄到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.common.validators import (
    PriceValidator,
    MarginValidator,
    InstitutionalValidator,
    LendingValidator
)
from services.common.utils.logger import setup_logger

logger = setup_logger(__name__)


# 資料類型對應的驗證器
VALIDATORS = {
    'price': PriceValidator,
    'margin': MarginValidator,
    'institutional': InstitutionalValidator,
    'lending': LendingValidator
}


def get_data_file_path(data_type: str, date: str, base_dir: str = 'data/raw') -> Path:
    """
    取得資料檔案路徑

    Args:
        data_type: 資料類型
        date: 日期 (YYYY-MM-DD)
        base_dir: 資料根目錄

    Returns:
        Path: 資料檔案路徑
    """
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    year = date_obj.strftime('%Y')
    month = date_obj.strftime('%m')

    file_path = Path(base_dir) / data_type / year / month / f"{date}.json"
    return file_path


def validate_file(file_path: str, data_type: str = None, quiet: bool = False) -> bool:
    """
    驗證單一檔案

    Args:
        file_path: 檔案路徑
        data_type: 資料類型，若為 None 則從路徑推測
        quiet: 靜默模式，不輸出詳細訊息

    Returns:
        bool: 驗證是否通過
    """
    file_path = Path(file_path)

    # 推測資料類型
    if data_type is None:
        for dtype in VALIDATORS.keys():
            if dtype in str(file_path):
                data_type = dtype
                break

    if data_type is None or data_type not in VALIDATORS:
        if not quiet:
            logger.error(f"無法推測資料類型或不支援的類型: {data_type}")
        return False

    if not quiet:
        logger.info(f"開始驗證: {file_path}")

    # 建立驗證器
    validator_class = VALIDATORS[data_type]
    validator = validator_class(str(file_path))

    # 執行驗證
    result = validator.validate()

    # 生成報告
    report_path = validator.generate_report()

    if not quiet:
        logger.info(f"驗證完成 - 狀態: {result.status}, 評分: {result.grade} ({result.accuracy:.1f}%)")
        logger.info(f"驗證報告: {report_path}")

    return result.status != 'FAIL'


def validate_date(date: str, types: list = None, base_dir: str = 'data/raw') -> dict:
    """
    驗證指定日期的資料

    Args:
        date: 日期 (YYYY-MM-DD)
        types: 要驗證的資料類型清單，若為 None 則驗證所有類型
        base_dir: 資料根目錄

    Returns:
        dict: 驗證結果 {data_type: success}
    """
    if types is None:
        types = list(VALIDATORS.keys())

    results = {}

    for data_type in types:
        file_path = get_data_file_path(data_type, date, base_dir)

        if not file_path.exists():
            logger.warning(f"檔案不存在: {file_path}")
            results[data_type] = False
            continue

        success = validate_file(str(file_path), data_type)
        results[data_type] = success

    return results


def validate_date_range(start_date: str, end_date: str, types: list = None,
                        base_dir: str = 'data/raw') -> dict:
    """
    驗證日期範圍的資料

    Args:
        start_date: 開始日期 (YYYY-MM-DD)
        end_date: 結束日期 (YYYY-MM-DD)
        types: 要驗證的資料類型清單
        base_dir: 資料根目錄

    Returns:
        dict: 驗證結果 {date: {data_type: success}}
    """
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    all_results = {}
    current = start

    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        logger.info(f"\n=== 驗證日期: {date_str} ===")

        results = validate_date(date_str, types, base_dir)
        all_results[date_str] = results

        current += timedelta(days=1)

    return all_results


def main():
    parser = argparse.ArgumentParser(
        description='資料驗證工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 驗證單一檔案
  python scripts/validate_data.py --file data/raw/price/2025/12/2025-12-28.json

  # 驗證指定日期
  python scripts/validate_data.py --date 2025-12-28

  # 驗證指定日期的特定類型
  python scripts/validate_data.py --date 2025-12-28 --types price margin

  # 驗證日期範圍
  python scripts/validate_data.py --start 2025-12-01 --end 2025-12-31

  # 驗證日期範圍的特定類型
  python scripts/validate_data.py --start 2025-12-01 --end 2025-12-31 --types price
        """
    )

    parser.add_argument(
        '--file',
        type=str,
        help='要驗證的檔案路徑'
    )

    parser.add_argument(
        '--type',
        type=str,
        choices=list(VALIDATORS.keys()),
        help='資料類型（與 --file 搭配使用，可省略會自動推測）'
    )

    parser.add_argument(
        '--quiet',
        action='store_true',
        help='靜默模式，只回傳狀態碼不輸出詳細訊息'
    )

    parser.add_argument(
        '--date',
        type=str,
        help='要驗證的日期 (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--start',
        type=str,
        help='開始日期 (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--end',
        type=str,
        help='結束日期 (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--types',
        type=str,
        nargs='+',
        choices=list(VALIDATORS.keys()),
        help='要驗證的資料類型 (可多選)'
    )

    parser.add_argument(
        '--base-dir',
        type=str,
        default='data/raw',
        help='資料根目錄 (預設: data/raw)'
    )

    args = parser.parse_args()

    # 驗證參數
    if args.file:
        # 驗證單一檔案
        success = validate_file(args.file, getattr(args, 'type', None), args.quiet)
        sys.exit(0 if success else 1)

    elif args.date:
        # 驗證指定日期
        results = validate_date(args.date, args.types, args.base_dir)

        # 顯示摘要
        print("\n=== 驗證摘要 ===")
        for data_type, success in results.items():
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{data_type:15s}: {status}")

        # 如果有任何失敗，回傳非零
        sys.exit(0 if all(results.values()) else 1)

    elif args.start and args.end:
        # 驗證日期範圍
        all_results = validate_date_range(args.start, args.end, args.types, args.base_dir)

        # 顯示摘要
        print("\n=== 驗證摘要 ===")
        total_validations = 0
        total_passed = 0

        for date, results in all_results.items():
            print(f"\n{date}:")
            for data_type, success in results.items():
                status = "✅ PASS" if success else "❌ FAIL"
                print(f"  {data_type:15s}: {status}")
                total_validations += 1
                if success:
                    total_passed += 1

        print(f"\n總計: {total_passed}/{total_validations} 通過 ({total_passed/total_validations*100:.1f}%)")

        sys.exit(0 if total_passed == total_validations else 1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
