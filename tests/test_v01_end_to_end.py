"""Release validation with synthetic workbooks and real Streamlit interactions."""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from src import pipeline
from src.ui_support import validation_table

MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
APP = Path(__file__).resolve().parents[1] / 'streamlit_app.py'


def synthetic_file(tmp_path):
    rows = [dict(Vernr=f'{i:03}', Vrad=1, Verdatum='2026-09-03', Utfall=10,
                 Konto='4000', Huvudtext='Syntetisk faktura') for i in range(1, 43)]
    rows += [dict(rows[0], Vrad=2, Utfall='felaktigt belopp'),
             dict(rows[0], Vernr='EXCLUDED', Konto='7698')]
    path = tmp_path / 'synthetic.xlsx'
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


def test_real_pipeline_order_and_source_immutability(tmp_path):
    source = synthetic_file(tmp_path)
    before, mtime = source.read_bytes(), source.stat().st_mtime_ns
    calls = []
    names = ['read_excel', 'map_columns', 'validate', 'filter_rows', 'build_verifications',
             'read_supplier_register', 'read_attestation_register', 'run_detection',
             'create_manual_sample', 'generate_reports']
    from contextlib import ExitStack
    with ExitStack() as stack:
        for name in names:
            original = getattr(pipeline, name)
            def record(*args, _name=name, _original=original, **kwargs):
                calls.append(_name)
                return _original(*args, **kwargs)
            stack.enter_context(patch.object(pipeline, name, side_effect=record))
        result = pipeline.run_pipeline(source, output_dir=tmp_path / 'reports')
    assert calls == names[:7] + ['run_detection'] * 42 + names[-2:]
    assert len(result.verifications) == 42
    assert len(result.verifications[0].rows) == 2
    assert [v.verification_id for v in result.manual_sample] == ['020', '040']
    assert all(c.status == 'NOT_CHECKED' for r in result.detection_results for c in r.checks)
    error = validation_table(result).iloc[0]
    assert error.verification_id == '001'
    assert error.verification_line_id == 2
    assert error.message.endswith('.')
    for path in result.report_paths.values():
        with pd.ExcelFile(path) as workbook:
            assert workbook.sheet_names
    assert source.read_bytes() == before
    assert source.stat().st_mtime_ns == mtime


def test_upload_analyze_download_rerun_and_error_recovery(tmp_path):
    source = synthetic_file(tmp_path)
    content, mtime = source.read_bytes(), source.stat().st_mtime_ns
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.file_uploader[0].set_value(('synthetic.xlsx', content, MIME)).run()
    app.button[0].click().run()
    assert not app.exception
    assert [b.label.split('**')[1] for b in app.button
            if b.key and b.key.startswith('kpi_')] == ['44', '43', '1', '0', '1']
    assert {b.key: b.label for b in app.button
            if b.key and b.key.startswith('control_')} == {
        'control_analyzed': '**42**  \nAnalyserade',
        'control_flagged': '**0**  \nFlaggade',
        'control_validation': '**1**  \nValideringsfel',
        'control_not_checked': '**168**  \nEj kontrollerade',
    }
    review = app.session_state['review']
    download_labels = {
        'granskning.xlsx': 'Kvar för granskning',
        'bortfiltrerade.xlsx': 'Bortfiltrerade',
        'samlad_kontrollfil.xlsx': 'Samlad kontrollfil',
        'flagged_invoices.xlsx': 'Hämta avvikelserapport',
        'manual_sample.xlsx': 'Hämta manuellt stickprov',
    }
    for index, filename in enumerate(download_labels):
        assert app.download_button[index].label == download_labels[filename]
        app.download_button[index].click().run()
        assert not app.exception
        with pd.ExcelFile(BytesIO(review.downloads[filename])) as workbook:
            assert workbook.sheet_names
    assert len(pd.read_excel(BytesIO(review.downloads['manual_sample.xlsx']))) == 2
    app.button[0].click().run()
    assert not app.exception
    app.file_uploader[0].set_value(('bad.xlsx', b'not excel', MIME)).run()
    assert not any(b.key and b.key.startswith(('kpi_', 'control_')) for b in app.button)
    app.button[0].click().run()
    assert not app.exception
    assert 'Analysen kunde inte slutföras' in app.error[0].value
    assert len(app.download_button) == 0
    app.file_uploader[0].set_value(('synthetic.xlsx', content, MIME)).run()
    app.button[0].click().run()
    assert not app.exception
    assert len(app.download_button) == 5
    assert source.read_bytes() == content
    assert source.stat().st_mtime_ns == mtime
