"""Streamlit presentation of supplier matching, candidate and contract evidence."""
import pandas as pd
import streamlit as st

from src.ui_support import display_dataframe

STATUS_LABELS = {
    'STRONG_MATCH': '🟢 Stark leverantörsträff',
    'AMBIGUOUS_MATCH': '🟡 Möjlig/flera leverantörsträffar',
    'NO_MATCH': '🟠 Ingen match i aktuellt Koncerninköpsregister',
    'SUPPLIER_NOT_IDENTIFIED': '⚪ Leverantör kunde inte identifieras',
}


def show_supplier_summary(analysis):
    if analysis is None:
        return
    st.subheader('Leverantörsmatchning mot Koncerninköp')
    for issue in analysis.registry.issues:
        st.warning(issue)
    if not analysis.registry.available:
        st.error('Leverantörsmatchningen kunde inte genomföras. Kontrollera registret och kolumnmappningen.')
        return
    st.caption(f'Registerutdrag: {analysis.registry.snapshot_date or "datum saknas"}. '
               'En leverantörsträff visar möjliga avtal. Vilket avtal köpet avser är inte bedömt.')
    for column, (label, count) in zip(st.columns(6), analysis.summary().items()):
        column.metric(label, count)
    unknown_dates = int((analysis.rows['registry_date_check'] == 'UNKNOWN').sum())
    if unknown_dates:
        st.warning(f'{unknown_dates} rader kunde inte datumkontrolleras. Se raddetaljer.')


def supplier_review_table(kept, analysis):
    display = kept.copy(deep=True)
    if analysis is None or not analysis.registry.available:
        return display
    evidence = analysis.rows.set_index('source_row_position').reindex(kept.index)
    for field, label in [('supplier_match_status', 'Leverantörsträff'),
                         ('supplier_text_raw', 'Extraherad leverantör'),
                         ('matched_supplier_name', 'Matchad avtalsleverantör'),
                         ('contract_count', 'Antal möjliga avtal'),
                         ('registry_date_warning', 'Äldre register än transaktion')]:
        while label in display.columns:
            label = '_' + label
        values = evidence[field]
        display[label] = (values.map(STATUS_LABELS) if field == 'supplier_match_status' else values).tolist()
    return display


def show_supplier_detail(analysis, source_position):
    if analysis is None or not analysis.registry.available:
        return
    matches = analysis.rows[analysis.rows['source_row_position'] == source_position]
    if matches.empty:
        return
    row = matches.iloc[0]
    st.subheader(STATUS_LABELS[row['supplier_match_status']])
    st.text(row['supplier_match_reason'])
    if row['registry_date_message']:
        st.warning(row['registry_date_message'])
    details = [('Leverantör från Huvudtext', row['supplier_text_raw']),
               ('Normaliserad jämförelsetext', row['supplier_normalized']),
               ('Matchad leverantör', row['matched_supplier_name']),
               ('Organisationsnummer', row['matched_organization_number']),
               ('Matchningsmetod', row['supplier_match_method']),
               ('Matchningsscore', row['supplier_match_score']),
               ('Antal kandidater', row['candidate_count']), ('Antal avtal', row['contract_count'])]
    st.dataframe(display_dataframe(pd.DataFrame(details, columns=['Uppgift', 'Värde'])),
                 hide_index=True, width='stretch')
    st.caption('Score beskriver namnlikhet/prefixtäckning på skalan 0–1; det är ingen sannolikhet. '
               'Exakt träff har score 1. Metod och osäkerhetsorsaker styr bedömningen.')
    candidates = analysis.candidates[analysis.candidates['source_row_position'] == source_position]
    if not candidates.empty:
        with st.expander('Leverantörskandidater och matchningsorsaker'):
            st.dataframe(display_dataframe(candidates.drop(columns='source_row_position')),
                         hide_index=True, width='stretch')
    contracts = analysis.contracts[analysis.contracts['source_row_position'] == source_position]
    if not contracts.empty:
        with st.expander('Möjliga avtal – inget avtal har valts automatiskt'):
            st.caption('Alla registerposter för kandidaterna visas. Datum och kategori används '
                       'ännu inte för att bedöma vilket avtal fakturan avser.')
            st.dataframe(display_dataframe(contracts.drop(columns='source_row_position')),
                         hide_index=True, width='stretch')
