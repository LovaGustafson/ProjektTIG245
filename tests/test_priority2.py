"""Confirmed supplier diversity and isolated view classifications, synthetic data only."""
from copy import deepcopy
from io import BytesIO

import pandas as pd
import pytest
import yaml
from streamlit.testing.v1 import AppTest

from src.models.verification import Verification
from src.sampling.manual_sample import plan_manual_sample
from src.supplier_matching.view_scope import load_view_rules, classify_supplier_view, visible_supplier_analysis
from src.ui_support import analyze_upload
from tests.test_feature_package import invoices, registry, workbook, settings


def units(names):
    return [Verification(str(i), pd.DataFrame({
        'verification_id': [str(i)], 'verification_line_id': [1],
        'header_text': [f'{name} Prelb 1' if name else None],
        'counterparty': ['same metadata'],
    }, index=[i * 3])) for i, name in enumerate(names, 1)]


def test_normalized_supplier_uniqueness_forward_replacement_and_order():
    source = units(['A AB', 'Apoteket AB', 'B AB', '  APOTEKET Aktiebolag. ', 'C AB', 'D AB'])
    first = plan_manual_sample(source, interval=2)
    second = plan_manual_sample(source, interval=2)
    assert [v.verification_id for v in first.sample] == ['2', '5', '6']
    assert [v.verification_id for v in second.sample] == ['2', '5', '6']
    pd.testing.assert_frame_equal(first.decisions, second.decisions)
    assert first.decisions.decision.tolist() == [
        'NOT_CANDIDATE', 'SELECTED', 'NOT_CANDIDATE', 'DUPLICATE_SUPPLIER', 'SELECTED', 'SELECTED']
    assert first.decisions.loc[3, 'duplicate_of_population_position'] == 2
    assert first.decisions.loc[4, 'nominal_position'] == 4
    assert [v.rows.index.tolist() for v in first.sample] == [[6], [15], [18]]
    assert first.target_size == 3
    assert first.shortfall_message == ''


def test_shortfall_does_not_backfill_duplicates_or_wrap_to_earlier_positions():
    result = plan_manual_sample(units(['Unused AB', 'Same AB', 'SAME Aktiebolag',
                                      'Same AB.', 'Same AB', 'Same AB']), interval=2)
    assert len(result.sample) == 1
    assert result.target_size == 3
    assert '1 av önskade 3' in result.shortfall_message
    assert 'Återstående platser fylls inte med dubletter' in result.shortfall_message
    assert result.decisions.loc[0, 'decision'] == 'NOT_CANDIDATE'
    assert result.decisions.loc[2, 'decision'] == 'NOT_CANDIDATE'


@pytest.mark.parametrize('names,expected', [
    (['A AB', 'A AB', None, None, None, 'B AB', 'C AB', 'D AB'], ['2', '6', '7', '8']),
    (['A AB', 'A AB', 'A AB', 'A AB', 'B AB'], ['2', '5']),
])
def test_forward_search_can_cross_nominal_positions_and_use_tail_without_revisiting(names, expected):
    result = plan_manual_sample(units(names), interval=2)
    assert [v.verification_id for v in result.sample] == expected
    assert len(result.sample) == result.target_size
    selected = result.decisions.loc[result.decisions.decision == 'SELECTED']
    assert selected.population_position.is_unique
    assert selected.population_position.is_monotonic_increasing


def test_missing_multiple_and_mixed_identity_units_are_explained_without_mutation():
    source = units(['A AB', None, 'B AB', 'C AB', 'D AB', 'E AB'])
    source[3].rows = pd.concat([source[3].rows, units(['Other AB'])[0].rows])
    before = deepcopy(source)
    result = plan_manual_sample(source, interval=2)
    assert [v.verification_id for v in result.sample] == ['3', '5', '6']
    assert result.decisions.loc[1, 'decision'] == 'UNUSABLE_IDENTITY'
    assert 'saknas' in result.decisions.loc[1, 'selection_reason']
    assert 'flera' in result.decisions.loc[3, 'selection_reason']
    for actual, expected in zip(source, before):
        pd.testing.assert_frame_equal(actual.rows, expected.rows)


def test_strong_aliases_share_organization_key_and_matching_is_unchanged(tmp_path):
    data = invoices(6)
    data.Huvudtext = ['Alfa AB Prelb 1', 'Beta AB Prelb 1', 'Alfa AB Prelb 1',
                     'Beta Namn AB Prelb 1', 'Gamma AB Prelb 1', 'Delta AB Prelb 1']
    register = pd.DataFrame({'Leverantör': ['Alfa AB', 'Beta AB', 'Beta Namn AB', 'Gamma AB', 'Delta AB'],
                             'Organisationsnummer': ['1', '2', '2', '3', '4']})
    path = settings(tmp_path)
    config = yaml.safe_load(path.read_text())
    config['manual_sample_interval'] = 2
    path.write_text(yaml.safe_dump(config))
    upload = analyze_upload(workbook(data), registry_mode='uploaded', registry_content=workbook(register), settings_path=path)
    result = upload.result
    before = deepcopy(result.supplier_analysis)
    assert [v.verification_id for v in result.manual_sample] == ['2', '5', '6']
    assert result.sampling_result.decisions.loc[3, 'decision'] == 'DUPLICATE_SUPPLIER'
    assert result.sampling_result.identity_rows.loc[3, 'supplier_key'] == 'org:2'
    assert result.supplier_analysis.rows.supplier_match_status.tolist() == ['STRONG_MATCH'] * 6
    assert result.sampling_evidence.population_position.tolist() == [2, 5, 6]
    report = pd.read_excel(BytesIO(upload.downloads['manual_sample.xlsx']), sheet_name=None)
    assert report['Urvalspositioner'].population_position.tolist() == [2, 5, 6]
    assert report['Urvalsbeslut'].decision.tolist() == result.sampling_result.decisions.decision.tolist()
    assert report['Källspårning'].source_row_position.tolist() == [1, 4, 5]
    plan_manual_sample(result.verifications, interval=2, supplier_analysis=result.supplier_analysis)
    for field in ('rows', 'candidates', 'contracts'):
        pd.testing.assert_frame_equal(getattr(result.supplier_analysis, field), getattr(before, field))


def rule(**kwargs):
    return dict(id='synthetic-confirmed', match_field='supplier_name', value='Synthetic AB',
                classification='INTERNAL', reason='Bekräftad syntetisk vyavgränsning.', confirmed=True, **kwargs)


def write_rules(path, rules, *, interval=20):
    config = yaml.safe_load(path.read_text())
    config.update(supplier_view_rules=rules, manual_sample_interval=interval)
    path.write_text(yaml.safe_dump(config, allow_unicode=True))


def test_view_classification_is_explicit_exact_and_independent_of_sampling(tmp_path):
    data = invoices(4)
    data.Huvudtext = ['Synthetic AB Prelb 1', 'Synthetic External AB Prelb 1',
                     'Another AB Prelb 1', 'Unclassified AB Prelb 1']
    data['Motp'] = 'Synthetic AB'
    content = workbook(data)
    path = settings(tmp_path)
    write_rules(path, [], interval=1)
    before = analyze_upload(content, registry_mode='disabled', settings_path=path)
    write_rules(path, [rule()], interval=1)
    after = analyze_upload(content, registry_mode='disabled', settings_path=path)
    classification = after.result.supplier_view
    assert classification.classification.tolist() == ['INTERNAL'] + ['UNCLASSIFIED'] * 3
    assert classification.excluded_from_view.tolist() == [True, False, False, False]
    assert classification.rule_ids.iloc[0] == 'synthetic-confirmed'
    assert classification.reason.iloc[0] == 'Bekräftad syntetisk vyavgränsning.'
    assert classification.source_row_position.tolist() == [0, 1, 2, 3]
    assert [v.verification_id for v in after.result.manual_sample] == ['1', '2', '3', '4']
    assert after.result.summary == before.result.summary
    pd.testing.assert_frame_equal(after.result.original_data, before.result.original_data)
    assert after.source_content == before.source_content
    pd.testing.assert_frame_equal(after.result.sampling_result.decisions, before.result.sampling_result.decisions)
    assert pd.read_excel(BytesIO(after.downloads['granskning.xlsx']), 'Granskning').shape[0] == 4
    assert pd.read_excel(BytesIO(after.downloads['granskning.xlsx']), 'Leverantörsvy').excluded_from_view.tolist() == [True, False, False, False]


def test_unconfirmed_rules_and_conflicts_do_not_hide_or_guess_external(tmp_path):
    path = settings(tmp_path)
    pending = {**rule(), 'confirmed': False}
    write_rules(path, [pending])
    data = pd.DataFrame({'header_text': ['Synthetic AB Prelb 1']}, index=[17])
    result = classify_supplier_view(data, None, load_view_rules(path))
    assert result.classification.tolist() == ['UNCLASSIFIED']
    assert not result.excluded_from_view.any()
    write_rules(path, [rule(), {**rule(), 'id': 'conflicting', 'classification': 'EXTERNAL'}])
    result = classify_supplier_view(data, None, load_view_rules(path))
    assert result.classification.tolist() == ['CONFLICT']
    assert not result.excluded_from_view.any()
    assert result.rule_ids.tolist() == ['synthetic-confirmed; conflicting']


def test_examples_are_not_automatically_classified_and_exact_base_rules_stay_separate():
    from src.filtering.internal_suppliers import internal_supplier_rule
    from src.filtering.filter_engine import load_exclusions, DEFAULT_SETTINGS_PATH
    names = ['Apoteket', 'Securitas', 'Försörjningsförvaltningen', 'Kantarellen']
    assert load_view_rules(DEFAULT_SETTINGS_PATH) == ()
    base = load_exclusions()['excluded_internal_suppliers']
    assert all(internal_supplier_rule(f'{name} Prelb 1', base) is None for name in names)
    assert internal_supplier_rule('Försörjningsförvaltning Prelb 1', base) == 'Försörjningsförvaltning'


@pytest.mark.parametrize('change', [
    {'match_field': 'counterparty'}, {'classification': 'GUESS'}, {'confirmed': 'true'}, {'value': ''},
])
def test_invalid_view_rules_fail_explicitly(tmp_path, change):
    path = settings(tmp_path)
    write_rules(path, [{**rule(), **change}])
    with pytest.raises(ValueError):
        load_view_rules(path)


def test_confirmed_organization_view_rule_preserves_accuracy_and_inspectable_rows(tmp_path):
    from pathlib import Path
    from src.ui_run_summary import dashboard_tables
    data = invoices(3)
    data.loc[2, 'Huvudtext'] = 'Separat Leverantör AB Prelb 1'
    register = pd.concat([registry(), registry('Separat Leverantör AB').assign(Organisationsnummer='456')])
    content, reference = workbook(data), workbook(register)
    path = settings(tmp_path)
    write_rules(path, [], interval=1)
    before = analyze_upload(content, registry_mode='uploaded', registry_content=reference, settings_path=path)
    write_rules(path, [{**rule(), 'match_field': 'organization_number', 'value': '1-23'}], interval=1)
    upload = analyze_upload(content, registry_mode='uploaded', registry_content=reference, settings_path=path)
    result = upload.result
    assert result.supplier_view.excluded_from_view.tolist() == [True, True, False]
    assert [v.verification_id for v in result.manual_sample] == ['1', '3']  # View rule does not alter sampling.
    assert len(result.manual_sample) < result.sampling_result.target_size == 3
    for field in ('rows', 'candidates', 'contracts'):
        pd.testing.assert_frame_equal(getattr(result.supplier_analysis, field), getattr(before.result.supplier_analysis, field))
    assert result.summary == before.result.summary
    scoped = visible_supplier_analysis(result.supplier_analysis, result.supplier_view)
    assert scoped.rows.source_row_position.tolist() == [2]
    assert scoped.candidates.source_row_position.tolist() == [2]
    assert scoped.contracts.source_row_position.tolist() == [2]
    charts = dashboard_tables(result)
    assert charts['suppliers'].Antal.sum() == 1
    assert charts['contracts'].Antal.sum() == 3  # Whole-run contract evidence is unchanged.
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'streamlit_app.py'), default_timeout=25)
    app.session_state['review'] = upload
    app.run()
    assert not app.exception
    assert any('exkluderade från denna vy: 2 källrader' in c.value for c in app.caption)
    scope = next(e for e in app.expander if e.label.startswith('Vyavgränsning'))
    assert not scope.proto.expanded
    assert scope.dataframe[0].value.source_row_position.tolist() == [0, 1]
    assert scope.dataframe[0].value.reason.tolist() == [rule()['reason']] * 2
    assert scope.dataframe[1].value.Vernr.tolist() == ['1', '2']
    assert any('Stickprovet blev mindre: 2 av önskade 3' in w.value for w in app.warning)
    assert app.tabs[0].dataframe[0].value.Vernr.tolist() == ['1', '2', '3']
    app.button(key='supplier_all').click().run()
    assert not app.exception
    assert app.tabs[0].dataframe[0].value.Vernr.tolist() == ['3']
    assert app.button(key='supplier_STRONG_MATCH').label.startswith('**1**')
    assert app.tabs[4].dataframe[0].value.Vernr.tolist() == ['1', '3']
    exported = pd.read_excel(BytesIO(upload.downloads['manual_sample.xlsx']), sheet_name=None)
    assert '2 av önskade 3' in exported['Urvalsmetod']['Förklaring till mindre stickprov'].iloc[0]
    assert exported['Urvalsidentiteter'].source_row_position.tolist() == [0, 1, 2]
    assert exported['Urvalsbeslut'].decision.tolist() == ['SELECTED', 'DUPLICATE_SUPPLIER', 'SELECTED']


def test_organization_rule_does_not_use_ambiguous_candidates(tmp_path):
    data = invoices(1).assign(Huvudtext='Input interiör Prelb 1')
    register = pd.DataFrame({'Leverantör': ['Input interiör AB', 'Input interiör Göteborg AB'],
                             'Organisationsnummer': ['123', '456']})
    path = settings(tmp_path)
    write_rules(path, [{**rule(), 'match_field': 'organization_number', 'value': '123'}], interval=1)
    result = analyze_upload(workbook(data), registry_content=workbook(register),
                            registry_mode='uploaded', settings_path=path).result
    assert result.supplier_analysis.rows.supplier_match_status.tolist() == ['AMBIGUOUS_MATCH']
    assert result.supplier_view.classification.tolist() == ['UNCLASSIFIED']
    assert not result.supplier_view.excluded_from_view.any()
    assert result.sampling_result.identity_rows.supplier_key.tolist() == ['name:input interiör']
    assert result.sampling_result.identity_rows.identity_basis.tolist() == ['NORMALIZED_HEADER_NAME']
