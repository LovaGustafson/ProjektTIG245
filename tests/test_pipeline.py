from datetime import datetime
import subprocess
import sys
from pathlib import Path

import pandas as pd
from src import pipeline
from src.models.result import CheckResult, CheckStatus
from src.ingestion.excel_reader import read_excel


def source(tmp_path):
    path = tmp_path / 'source.xlsx'
    pd.DataFrame({
        'Vernr': ['001', '001', '002', '003', None],
        'Vrad': [1, 2, 1, 1, 1],
        'Verdatum': [datetime(2026, 9, 3)] * 5,
        'Utfall': [10, 'invalid', 20, 30, 40],
        'Konto': ['4000', '4000', '7698', '4000', '4000'],
    }).to_excel(path, index=False)
    settings = tmp_path / 'settings.yaml'
    settings.write_text('excluded_accounts: ["7698", "7699"]\nexcluded_verification_types: null\nmanual_sample_interval: 2\n')
    return path, settings


def test_complete_run_filtering_invalid_rows_and_unresolved_rules(tmp_path):
    path, settings = source(tmp_path)
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    result = pipeline.run_pipeline(path, settings_path=settings, output_dir=tmp_path / 'out')
    assert [v.verification_id for v in result.verifications] == ['001', '003']
    assert len(result.verifications[0].rows) == 2
    assert result.validation.rows[1].validation_status == 'INVALID'
    assert result.validation.rows[1].validation_errors
    assert len(result.ungrouped_data) == 1
    assert all(check.status == CheckStatus.NOT_CHECKED
               for detection in result.detection_results for check in detection.checks)
    assert result.manual_sample == []  # No Huvudtext supplier identity in this fixture.
    assert result.sampling_result.decisions.iloc[1]['decision'] == 'UNUSABLE_IDENTITY'
    assert '0 av önskade 1' in result.sampling_result.shortfall_message
    assert all(p.exists() for p in result.report_paths.values())
    assert len(read_excel(result.report_paths['cleaned_data'])) == 4
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime


def test_all_analysis_before_sampling_and_multiple_reasons(tmp_path, monkeypatch):
    path, settings = source(tmp_path)
    analyzed = []
    def synthetic_rule(v, context):
        analyzed.append(v.verification_id)
        assert '7698' not in v.rows['account'].tolist()
        return [CheckResult(v.verification_id, 'synthetic', CheckStatus.FLAGGED, reason)
                for reason in ['First', 'Second']]
    real_sample = pipeline.plan_manual_sample
    def sample(*args, **kwargs):
        assert analyzed == ['001', '003']
        return real_sample(*args, **kwargs)
    monkeypatch.setattr(pipeline, 'plan_manual_sample', sample)
    result = pipeline.run_pipeline(path, settings_path=settings, output_dir=tmp_path / 'out',
                                   rules={'synthetic': synthetic_rule})
    assert result.detection_results[0].flag_reasons == ('First', 'Second')
    assert read_excel(result.report_paths['flagged_invoices'], sheet_name='checks')['reason'].tolist() == ['First', 'Second'] * 2


def test_reader_failures_and_rule_failure_do_not_stop_later_verifications(tmp_path):
    path, settings = source(tmp_path)
    def broken(v, context):
        raise ValueError('synthetic failure')
    result = pipeline.run_pipeline(path, settings_path=settings, output_dir=tmp_path / 'out',
        supplier_register=tmp_path / 'missing.csv',
        image_references={'001': [tmp_path / 'missing.png']}, rules={'broken': broken})
    assert len(result.detection_results) == 2
    assert all(r.status == CheckStatus.ERROR for r in result.detection_results)
    assert result.detection_results[0].context.image_results[0].status == 'MISSING_FILE'


def test_local_entry_point(tmp_path):
    path, settings = source(tmp_path)
    completed = subprocess.run([sys.executable, 'src/main.py', str(path), '--settings', str(settings),
                               '--output-dir', str(tmp_path / 'cli')],
                              cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert 'Analyzed: 2' in completed.stdout
    assert 'NOT_CHECKED' in completed.stdout


def test_empty_workbook_generates_empty_reports(tmp_path):
    path = tmp_path / 'empty.xlsx'
    pd.DataFrame(columns=['Vernr', 'Vrad', 'Verdatum', 'Utfall', 'Konto']).to_excel(path, index=False)
    result = pipeline.run_pipeline(path, output_dir=tmp_path / 'out')
    assert result.verifications == []
    assert result.detection_results == []
    assert result.manual_sample == []
    assert all(p.exists() for p in result.report_paths.values())
