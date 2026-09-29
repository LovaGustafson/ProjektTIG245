"""Visual presentation of existing run evidence; no selection or business rules."""
import pandas as pd
import streamlit as st

from src.models.result import CheckStatus
from src.models.supplier import SupplierMatchStatus
from src.run_summary import SAMPLE_ORDER, SAMPLE_POPULATION


SUPPLIER_LABELS = {
    'STRONG_MATCH': 'Stark leverantörsträff',
    'AMBIGUOUS_MATCH': 'Osäker träff',
    'NO_MATCH': 'Ingen träff i registret',
    'SUPPLIER_NOT_IDENTIFIED': 'Leverantör ej identifierad',
}
CHECK_LABELS = {
    'PASS': 'Utan flagga', 'FLAGGED': 'Flaggad',
    'ERROR': 'Tekniskt fel', 'NOT_CHECKED': 'Ej kontrollerad',
}
CONTRACT_LABELS = {
    'PASS': 'Inom avtalsperiod', 'FLAGGED': 'Utanför avtalsperiod',
    'ERROR': 'Tekniskt fel', 'NOT_CHECKED': 'Ej verifierbar',
}
EXCLUSION_LABELS = {
    'account': 'Konto', 'verification_type': 'Verifikationstyp',
    'internal_supplier': 'Intern leverantör', 'structural_row': 'Strukturell rad',
}
STATUS_COLORS = ['#126b78', '#b66a12', '#b33d4b', '#788494']


def _counts_table(counts, labels):
    """Retain evidence keys alongside readable labels, including zero counts."""
    return pd.DataFrame([
        {'Kategori': labels.get(key, key), 'Antal': int(value), 'Status': str(key)}
        for key, value in counts.items()
    ], columns=['Kategori', 'Antal', 'Status'])


def dashboard_tables(result):
    """Build display copies from the same RunSummary/evidence used by exports.

    Exclusions are recorded rule hits (potentially overlapping). Supplier counts
    are occurrences, checks are individual results, contracts are comparisons.
    An unavailable register supplies no supplier-status distribution.
    """
    s = result.summary
    if s is None:
        return {}
    exclusion_labels = {}
    for rule in s.exclusion_counts:
        kind, _, expression = rule.partition(': ')
        exclusion_labels[rule] = f'{EXCLUSION_LABELS.get(kind, kind)} – {expression}'
    analysis = result.supplier_analysis
    supplier_counts = {}
    if analysis is not None and analysis.registry.available:
        counts = analysis.rows['supplier_match_status'].value_counts()
        supplier_counts = {status.value: counts.get(status, 0) for status in SupplierMatchStatus}
    return {
        'population': _counts_table(
            {'included': s.included_rows, 'excluded': s.excluded_rows},
            {'included': 'Kvarvarande', 'excluded': 'Exkluderade'}),
        'exclusions': _counts_table(s.exclusion_counts, exclusion_labels),
        'suppliers': _counts_table(supplier_counts, SUPPLIER_LABELS),
        'checks': _counts_table(
            {status.value: s.check_status_counts.get(status, 0) for status in CheckStatus}, CHECK_LABELS),
        'contracts': _counts_table(
            {status.value: s.contract_status_counts.get(status, 0) for status in CheckStatus}, CONTRACT_LABELS),
        'sample': _counts_table(
            {'selected': s.sampled_verifications,
             'remaining': s.eligible_verifications - s.sampled_verifications},
            {'selected': 'Utvalda', 'remaining': 'Övriga i urvalspopulationen'}),
    }


def show_count_chart(data, *, unit, key, colors=None, empty_message):
    """Native Streamlit/Vega-Lite bars with exact values, labels and tooltips."""
    if data.empty or not data['Antal'].sum():
        st.info(empty_message)
        return
    spec = {
        'height': max(120, len(data) * 44),
        'padding': {'right': 35},
        'encoding': {
            'y': {'field': 'Kategori', 'type': 'nominal', 'sort': None,
                  'axis': {'title': None, 'labelLimit': 230}},
            'x': {'field': 'Antal', 'type': 'quantitative',
                  'scale': {'zero': True, 'nice': True},
                  'axis': {'title': unit, 'tickMinStep': 1, 'format': 'd'}},
            'tooltip': [{'field': 'Kategori', 'type': 'nominal'},
                        {'field': 'Antal', 'type': 'quantitative', 'title': unit, 'format': 'd'}],
        },
        'layer': [
            {'mark': {'type': 'bar', 'cornerRadiusEnd': 4, 'size': 23},
             'encoding': {'color': {'field': 'Status', 'type': 'nominal', 'legend': None,
                          'scale': {'domain': data['Status'].tolist(),
                                    'range': colors or ['#126b78'] * len(data)}}}},
            {'mark': {'type': 'text', 'align': 'left', 'dx': 7},
             'encoding': {'text': {'field': 'Antal', 'type': 'quantitative', 'format': 'd'}}},
        ],
    }
    st.vega_lite_chart(data, spec, width='stretch', key=key)


def show_run_summary(result):
    s = result.summary
    if s is None:
        return
    charts = dashboard_tables(result)
    st.subheader('Analysöversikt')
    st.caption('Hela analyskörningen. Tillfälliga vyfilter ändrar inte dessa antal eller exporterna.')
    with st.container(key='overview_kpis'):
        for column, label, value in zip(st.columns(5),
                ['Källpopulation · rader', 'Kvarvarande · rader', 'Exkluderade · rader',
                 'Flaggade · verifikationer', 'Manuellt urval · verifikationer'],
                [s.source_rows, s.included_rows, s.excluded_rows,
                 s.flagged_verifications, s.sampled_verifications]):
            column.metric(label, value)

    st.html('<ol class="audit-steps" aria-label="Analysens steg">'
            '<li><span>1</span>Källfil</li><li><span>2</span>Filtrering → kvarvarande</li>'
            '<li><span>3</span>Leverantörsmatchning</li><li><span>4</span>Avtalsperioder</li>'
            '<li><span>5</span>Kontrollresultat</li><li><span>6</span>Stickprov / export</li></ol>')
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown('#### Populationens flöde')
        st.caption(f'{s.source_rows} källrader = {s.included_rows} kvarvarande + {s.excluded_rows} exkluderade.')
        show_count_chart(charts['population'], unit='Källrader', key='chart_population',
                         colors=['#126b78', '#788494'], empty_message='Inga inlästa källrader.')
        st.caption('Avser den inlästa tabellen i första kalkylbladet. '
                   'Fullständighet gentemot Proceedo är inte verifierad.')
    with right, st.container(border=True):
        st.markdown('#### Leverantörsmatchning')
        analysis = result.supplier_analysis
        if analysis is None or not analysis.registry.available:
            st.info(f'Matchning ej tillgänglig för {s.supplier_unavailable_rows} kvarvarande rader. '
                    'Register saknas eller är oanvändbart.')
        else:
            show_count_chart(charts['suppliers'], unit='Kvarvarande rader', key='chart_suppliers',
                             colors=['#126b78', '#b66a12', '#b33d4b', '#788494'],
                             empty_message='Inga kvarvarande rader att matcha.')
        st.caption(f'{s.uncertain_supplier_rows} rader utan säker leverantörsträff. '
                   'Leverantörsidentitet är separat från avtalsefterlevnad. Detaljer finns under Granskning.')

    with st.container(border=True):
        st.markdown('#### Varför exkluderades rader?')
        st.caption('Faktiska regelträffar. En rad kan träffa flera regler; staplarna ska inte summeras '
                   'till antal unika exkluderade rader.')
        show_count_chart(charts['exclusions'], unit='Regelträffar (rader)', key='chart_exclusions',
                         empty_message='Inga exkluderingsorsaker i denna körning.')

    st.subheader('Avvikelser och kontrollstatus')
    st.caption(f'{s.flagged_verifications} flaggade verifikationer med {s.flagged_rows} tillhörande rader. '
               'Ej kontrollerat är varken godkänt eller en konstaterad avvikelse. '
               'Tekniska fel redovisas separat.')
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown('#### Detektionskontroller')
        show_count_chart(charts['checks'], unit='Kontrollresultat', key='chart_checks',
                         colors=STATUS_COLORS, empty_message='Inga kontrollresultat i denna körning.')
        st.caption('Flera kontroller kan avse samma verifikation. Orsaker och teknisk validering finns i detaljvyerna.')
    with right, st.container(border=True):
        st.markdown('#### Avtalsperioder vid verifikationsdatum')
        show_count_chart(charts['contracts'], unit='Avtalsjämförelser', key='chart_contracts',
                         colors=STATUS_COLORS, empty_message='Inga avtalsjämförelser kunde göras i denna körning.')
        st.caption('Varje möjligt registeravtal jämförs separat med källradens datum. '
                   'Inom perioden betyder inte att köpet omfattas av avtalet.')

    with st.container(border=True, key='sample_overview'):
        st.subheader('Manuellt stickprov')
        for column, label, value in zip(st.columns(4),
                ['Verifikationer i urvalspopulationen', 'Stickprovsintervall',
                 'Valda verifikationer', 'Rader i stickprovet'],
                [s.eligible_verifications, f'1 av {s.sample_interval}', s.sampled_verifications, s.sampled_rows]):
            column.metric(label, value)
        show_count_chart(charts['sample'], unit='Verifikationer', key='chart_sample',
                         colors=['#126b78', '#b7c4d2'], empty_message='Urvalspopulationen är tom.')
        st.caption(SAMPLE_POPULATION + ' ' + SAMPLE_ORDER)
        st.caption('Granskningsstatus registreras inte i verktyget. Antal färdiggranskade kan därför inte visas. '
                   'Se urvalet under Manuell kontroll och hämta underlaget under Export.')
        if s.ungrouped_rows:
            st.warning(f'{s.ungrouped_rows} kvarvarande rader saknar användbart verifikations-ID. '
                       'De finns i granskningsunderlaget men ingår inte i det verifikationsbaserade stickprovet.')
