"""Streamlit presentation of supplier matching, candidate and contract evidence."""
import pandas as pd
import streamlit as st

from src.ui_support import display_dataframe
from src.ui_navigation import select_drilldown
from src.supplier_matching.contract_period import ACTIVE, NOT_STARTED, ENDED, UNVERIFIABLE

STATUS_LABELS = {
    'STRONG_MATCH': '🟢 Stark leverantörsträff',
    'AMBIGUOUS_MATCH': '🟡 Osäker träff – manuell granskning',
    'NO_MATCH': '🟠 Ingen match i aktuellt Koncerninköpsregister',
    'SUPPLIER_NOT_IDENTIFIED': '⚪ Leverantör kunde inte identifieras',
}

SUPPLIER_VIEWS = ('all', *STATUS_LABELS, 'date_warning')


def supplier_positions(analysis, key):
    rows = analysis.rows
    if key == 'date_warning':
        rows = rows[rows['registry_date_warning'].astype(bool)]
    elif key != 'all':
        rows = rows[rows['supplier_match_status'] == key]
    return rows['source_row_position'].tolist()


def show_supplier_summary(analysis):
    if analysis is None:
        return
    st.subheader('Leverantörsmatchning mot Koncerninköp')
    for issue in analysis.registry.issues:
        st.warning(issue)
    if not analysis.registry.available:
        message = 'Leverantörsmatchningen kunde inte genomföras. Kontrollera registret och kolumnmappningen.'
        if analysis.registry.source_sha256 is None and analysis.registry.source_kind in ('default', 'disabled'):
            st.info(message)
        else:
            st.error(message)
        return
    st.caption(f'Registerutdrag: {analysis.registry.snapshot_date or "datum saknas"}. '
               'En leverantörsträff visar möjliga avtal. Vilket avtal köpet avser är inte bedömt.')
    with st.container(key='supplier_kpis'):
        for column, key, (label, count) in zip(st.columns(6), SUPPLIER_VIEWS, analysis.summary().items()):
            column.button(f'**{count}**  \n{label}', key='supplier_' + key, width='stretch',
                          on_click=select_drilldown, args=('selected_supplier', key, 'review_rows'),
                          type='primary' if st.session_state.get('selected_supplier') == key else 'secondary')
    unknown_dates = int((analysis.rows['registry_date_check'] == 'UNKNOWN').sum())
    if unknown_dates:
        st.warning(f'{unknown_dates} rader kunde inte datumkontrolleras. Se raddetaljer.')
    st.markdown('**Avtalsperioder vid verifikationsdatum**')
    counts = analysis.contracts['contract_period_result'].value_counts()
    for label in (ACTIVE, NOT_STARTED, ENDED, UNVERIFIABLE):
        st.text(f'{label}: {int(counts.get(label, 0))} avtalsjämförelser')
    st.caption('Varje registeravtal jämförs separat med källradens datum. Flera avtal kan finnas per rad. '
               'En aktiv period bevisar inte att köpet omfattas av avtalet. '
               'Ej verifierbara perioder är inte konstaterade avvikelser.')


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
        if field == 'supplier_match_status':
            values = values.map(STATUS_LABELS)
        elif field == 'registry_date_warning':
            values = values.map({True: '🟣 Registerdatumvarning', False: '—'})
        display[label] = values.tolist()
    return display


def show_supplier_detail(analysis, source_position):
    if analysis is None or not analysis.registry.available:
        return
    matches = analysis.rows[analysis.rows['source_row_position'] == source_position]
    if matches.empty:
        return
    row = matches.iloc[0]
    st.subheader(STATUS_LABELS[row['supplier_match_status']])
    colors = {'STRONG_MATCH': 'green', 'AMBIGUOUS_MATCH': 'yellow',
              'NO_MATCH': 'orange', 'SUPPLIER_NOT_IDENTIFIED': 'gray'}
    st.badge(STATUS_LABELS[row['supplier_match_status']], color=colors[row['supplier_match_status']])
    st.text(row['supplier_match_reason'])
    if row['supplier_match_status'] == 'STRONG_MATCH':
        st.caption('Leverantören är starkt identifierad i aktuellt register. '
                   'Detta bedömer inte fakturans riktighet eller om köpet omfattas av avtal.')
    elif row['supplier_match_status'] == 'NO_MATCH':
        st.text('Sökt leverantörsnamn: ' + str(row['supplier_text_raw']))
    elif row['supplier_match_status'] == 'AMBIGUOUS_MATCH':
        st.warning('Manuell granskning krävs. Jämför kandidaterna och matchningsorsakerna nedan; '
                   'ingen leverantör har valts automatiskt.')
    if row['registry_date_warning']:
        st.badge('Registerdatumvarning', color='violet')
    if row['registry_date_message']:
        st.warning(row['registry_date_message'])
    else:
        st.caption('Ingen registerdatumvarning: transaktionen är inte senare än registerutdraget.')
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
        with st.expander('Leverantörskandidater och matchningsorsaker',
                         expanded=row['supplier_match_status'] == 'AMBIGUOUS_MATCH'):
            st.dataframe(display_dataframe(candidates.drop(columns='source_row_position')),
                         hide_index=True, width='stretch')
    contracts = analysis.contracts[analysis.contracts['source_row_position'] == source_position]
    if not contracts.empty:
        with st.expander('Möjliga avtal – inget avtal har valts automatiskt'):
            st.caption('Alla registerposter visas med originaldatum, använd period, verifikationsdatum '
                       'och kontrollresultat. Osäker identitet eller oklara datum ger NOT_CHECKED. '
                       'Vilket avtal köpet omfattas av har inte avgjorts.')
            st.dataframe(display_dataframe(contracts.drop(columns='source_row_position')),
                         hide_index=True, width='stretch', column_config={
                             'contract_id': 'Avtals-ID', 'contract_name': 'Avtalsnamn',
                             'start_date': 'Startdatum (original)', 'end_date': 'Slutdatum (original)',
                             'final_end_date': 'Sista slutdatum (original)',
                             'verification_date': 'Verifikationsdatum (original)',
                             'evaluated_start_date': 'Använd period från', 'evaluated_end_date': 'Använd period till',
                             'contract_period_result': 'Avtalsperiod vid verifikationsdatum',
                             'contract_period_reason': 'Motivering',
                         })
