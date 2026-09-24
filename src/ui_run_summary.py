"""Present run counts with explicit units and without inferring review progress."""
import streamlit as st

from src.run_summary import SAMPLE_ORDER, SAMPLE_POPULATION


def show_run_summary(result):
    summary = result.summary
    if summary is None:
        return
    st.subheader('Körningsöversikt och manuellt urval')
    for column, label, value in zip(st.columns(4),
            ['Verifikationer i urvalspopulationen', 'Stickprovsintervall',
             'Valda verifikationer', 'Rader i stickprovet'],
            [summary.eligible_verifications, f'1 av {summary.sample_interval}',
             summary.sampled_verifications, summary.sampled_rows]):
        column.metric(label, value)
    st.caption(SAMPLE_POPULATION + ' ' + SAMPLE_ORDER)
    st.text(f'Källdata: {summary.source_rows} rader → filtrering: {summary.included_rows} kvar, '
            f'{summary.excluded_rows} exkluderade → leverantörsmatchning: '
            f'{summary.supplier_analyzed_rows} analyserade rader → avtalsperioder: '
            f'{sum(summary.contract_status_counts.values())} avtalsjämförelser → '
            f'flaggning: {summary.flagged_verifications} verifikationer '
            f'({summary.flagged_rows} tillhörande rader) → stickprov/export: '
            f'{summary.sampled_verifications} valda verifikationer.')
    if summary.ungrouped_rows:
        st.warning(f'{summary.ungrouped_rows} kvarvarande rader saknar användbart verifikations-ID. '
                   'De finns i granskningsunderlaget men ingår inte i det verifikationsbaserade stickprovet.')
    with st.expander('Exkluderingsorsaker och underlag för manuell granskning'):
        st.caption('Regelträffar kan överlappa. Totalt exkluderade räknar varje källrad en gång.')
        labels = {'account': 'Konto', 'verification_type': 'Verifikationstyp',
                  'internal_supplier': 'Intern leverantör', 'structural_row': 'Rapportrad'}
        for rule, count in summary.exclusion_counts.items():
            kind, _, expression = rule.partition(': ')
            st.text(f'{labels.get(kind, kind)} – {expression}: {count} rader')
        st.text(f'Utan säker leverantörsträff: {summary.uncertain_supplier_rows} rader, varav '
                f'{summary.supplier_unavailable_rows} inte kunde matchas eftersom register saknas eller är oanvändbart.')
        if result.supplier_analysis and result.supplier_analysis.registry.available:
            for label, count in result.supplier_analysis.summary().items():
                st.text(f'{label}: {count}')
        for status, count in summary.check_status_counts.items():
            label = {'PASS': 'Genomförda kontroller utan flagga', 'FLAGGED': 'Kontroller med flagga',
                     'ERROR': 'Kontroller med tekniskt fel', 'NOT_CHECKED': 'Ej genomförda kontroller'}[status]
            st.text(f'{label}: {count}')
        for status, count in summary.contract_status_counts.items():
            label = {'PASS': 'Inom avtalsperiod', 'FLAGGED': 'Utanför avtalsperiod',
                     'NOT_CHECKED': 'Avtalsperiod ej verifierbar', 'ERROR': 'Tekniskt fel i avtalskontroll'}[status]
            st.text(f'{label}: {count} avtalsjämförelser')
        st.caption('Ej genomförda kontroller är varken godkända kontroller eller konstaterade avvikelser. '
                   'Leverantörsmatchning och avtalsperioder redovisas separat från kontrollflaggor.')
