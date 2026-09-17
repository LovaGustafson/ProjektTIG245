"""Local entry point: python -m src.main INPUT.xlsx --output-dir NEW_DIRECTORY."""
import argparse
import logging
from pathlib import Path
import sys

# Also support the specification's python src/main.py invocation.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline import run_pipeline
from src.filtering.filter_engine import DEFAULT_SETTINGS_PATH


def main(argv=None):
    parser = argparse.ArgumentParser(description='Analyze a local invoice workbook.')
    parser.add_argument('input', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--settings', type=Path, default=DEFAULT_SETTINGS_PATH)
    parser.add_argument('--sheet', default=0, help='Worksheet name (default: first worksheet)')
    parser.add_argument('--supplier-register', type=Path)
    parser.add_argument('--registry-snapshot-date', help='Koncerninköp snapshot date, YYYY-MM-DD')
    parser.add_argument('--attestation-register', type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    try:
        result = run_pipeline(args.input, output_dir=args.output_dir,
                              settings_path=args.settings, sheet_name=args.sheet,
                              supplier_register=args.supplier_register,
                              registry_snapshot_date=args.registry_snapshot_date,
                              attestation_register=args.attestation_register)
    except Exception as exc:
        print(f'Pipeline failed ({type(exc).__name__}): {exc}', file=sys.stderr)
        return 1
    print(f'Analyzed: {len(result.detection_results)} verifications')
    print(f'Invalid rows: {sum(r.validation_status == "INVALID" for r in result.validation.rows)}')
    if result.supplier_analysis is not None:
        for label, count in result.supplier_analysis.summary().items():
            print(f'{label}: {count}')
    for check_result in result.detection_results:
        print(f'{check_result.verification_id}: {check_result.status}')
        for check in check_result.checks:
            print(f'  {check.check_type}: {check.status}: {check.reason}')
    for row in result.validation.rows:
        for error in row.validation_errors:
            print(f'Row {row.row_position}: {error.message}')
    for path in result.report_paths.values():
        print(path)
    for todo in result.todos:
        print(todo)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
