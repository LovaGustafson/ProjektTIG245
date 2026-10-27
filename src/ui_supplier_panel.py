"""Streamlit presentation of supplier matching, candidate and contract evidence."""
import pandas as pd
import streamlit as st

from src.ui_support import display_dataframe
from src.presentation import (
    customer_facing_value, REGISTRY_ORGANIZATION_COLUMNS,
    SUPPLIER_MATCH_EXPLANATION,
)
from src.ui_supplier_matches import MATCH_LABELS, match_explanation, show_supplier_candidates
from src.ui_navigation import select_drilldown
from src.ui_overview_details import source_rows
from src.supplier_matching.view_scope import visible_supplier_analysis
from src.supplier_matching.contract_period import ACTIVE, NOT_STARTED, ENDED, UNVERIFIABLE

STATUS_LABELS = {
    'STRONG_MATCH': '🟢 Stark namnmatchning',
    'AMBIGUOUS_MATCH': '🟡 Osäker namnmatchning – manuell granskning',
    'NO_MATCH': '🟠 Ingen match i aktuellt Koncerninköpsregister',
    'SUPPLIER_NOT_IDENTIFIED': '⚪ Leverantör kunde inte identifieras',
}

SUPPLIER_VIEWS = ('all', *STATUS_LABELS, 'date_warning')


def show_supplier_scope(result):
    classification = result.supplier_view
    if classification is None:
        return
    excluded = classification.loc[classification['excluded_from_view'].astype(bool)]
    st.caption(f'Interna/ej relevanta leverantörer exkluderade från denna vy: {len(excluded)} källrader. '
               'Avser endast bekräftade vyregler. Oklassificerad betyder inte extern. '
               'Hela granskningsunderlaget, matchningsresultaten och stickprovet bevaras.')
    with st.expander('Vyavgränsning – klassificering, exkluderade poster och orsaker', expanded=False):
        if excluded.empty:
            st.info('Inga källrader har exkluderats av bekräftade leverantörsvyregler.')
        else:
            st.dataframe(display_dataframe(excluded), hide_index=True, width='stretch')
            st.dataframe(display_dataframe(source_rows(result, excluded['source_row_position'])),
                         hide_index=True, width='stretch')
        with st.expander('Klassificering för alla kvarvarande källrader', expanded=False):
            st.dataframe(display_dataframe(classification), hide_index=True, width='stretch')
        st.caption('Basexkluderingar redovisas separat under Varför exkluderades rader? '
                   'Regler för denna vy finns i supplier_view_rules. Listan är tom tills '
                   'uttryckliga regler med motivering har bekräftats.')
    if classification['classification'].eq('CONFLICT').any():
        st.warning('Motstridiga leverantörsvyregler finns. Berörda rader visas och kan granskas i klassificeringen.')


def supplier_positions(analysis, key):
    rows = analysis.rows
    if key == 'date_warning':
        rows = rows[rows['registry_date_warning'].astype(bool)]
    elif key != 'all':
        rows = rows[rows['supplier_match_status'] == key]
    return rows['source_row_position'].tolist()


def show_supplier_summary(analysis, classification=None):
    if analysis is None:
        return
    full_analysis = analysis
    analysis = visible_supplier_analysis(analysis, classification)
    st.subheader('Leverantörsmatchning mot Koncerninköp')
    if not analysis.registry.available:
        message = 'Leverantörsmatchningen kunde inte genomföras. Kontrollera registret och kolumnmappningen.'
        if analysis.registry.source_sha256 is None and analysis.registry.source_kind in ('default', 'disabled'):
            st.info(message)
        else:
            st.error(message)
        return
    st.caption(f'Registerutdrag: {analysis.registry.snapshot_date or "datum saknas"}. '
               'En namnmatchning visar möjliga avtal. Vilket avtal köpet avser är inte bedömt.')
    st.caption(SUPPLIER_MATCH_EXPLANATION)
    with st.container(key='supplier_kpis'):
        for column, key, (label, count) in zip(st.columns(6), SUPPLIER_VIEWS, analysis.summary().items()):
            column.button(f'**{count}**  \n{label}', key='supplier_' + key, width='stretch',
                          on_click=select_drilldown, args=('selected_supplier', key, 'review_rows'),
                          type='primary' if st.session_state.get('selected_supplier') == key else 'secondary')
    unknown_dates = int((analysis.rows['registry_date_check'] == 'UNKNOWN').sum())
    if unknown_dates:
        st.warning(f'{unknown_dates} rader kunde inte datumkontrolleras. Se raddetaljer.')
    st.markdown('**Avtalsperioder vid verifikationsdatum**')
    counts = full_analysis.contracts['contract_period_result'].value_counts()
    for label in (ACTIVE, NOT_STARTED, ENDED, UNVERIFIABLE):
        st.text(f'{label}: {int(counts.get(label, 0))} avtalsjämförelser')
    st.caption('Avtalsjämförelserna avser hela körningen, oberoende av leverantörsvyn. '
               'Varje registeravtal jämförs separat med källradens datum. Flera avtal kan finnas per rad. '
               'En aktiv period bevisar inte att köpet omfattas av avtalet. '
               'Ej verifierbara perioder är inte konstaterade avvikelser.')


def supplier_review_table(kept, analysis):
    display = kept.copy(deep=True)
    if analysis is None or not analysis.registry.available:
        return display
    evidence = analysis.rows.set_index('source_row_position').reindex(kept.index)
    for field, label in [('supplier_text_raw', 'Leverantör i internkontrollsfilen'),
                         ('matched_supplier_name', 'Leverantör i avtalsregistret'),
                         ('supplier_match_status', 'Matchningsresultat'),
                         ('supplier_match_score', 'Matchningsscore'),
                         ('supplier_match_reason', 'Varför detta resultat?'),
                         ('contract_count', 'Antal möjliga avtal'),
                         ('registry_date_warning', 'Äldre register än transaktion')]:
        while label in display.columns:
            label = '_' + label
        values = evidence[field]
        if field == 'supplier_match_status':
            values = values.map(MATCH_LABELS)
        elif field == 'supplier_match_reason':
            values = evidence.apply(match_explanation, axis=1) if not evidence.empty else values
        elif field == 'registry_date_warning':
            values = values.map({True: '🟣 Registerdatumvarning', False: '—'})
        elif field == 'supplier_text_raw':
            values = values.map(lambda value: customer_facing_value(field, value)
                                if pd.notna(value) and str(value).strip() else 'Inget extraherat leverantörsnamn')
        elif field == 'matched_supplier_name':
            # Preserve the engine's ranking; displaying a candidate does not select an identity.
            candidates = analysis.candidates.groupby('source_row_position', sort=False).head(1)
            names = candidates.set_index('source_row_position')['supplier_name'].reindex(kept.index)
            names = names.map(lambda name: f'{name} (kandidat)' if pd.notna(name) else name)
            ambiguous = evidence['supplier_match_status'].eq('AMBIGUOUS_MATCH')
            values = values.where(~ambiguous, names).fillna('Ingen kandidat identifierad')
        display[label] = values.tolist()
    return display


def show_supplier_detail(analysis, source_position):
    if analysis is None or not analysis.registry.available:
        return
    matches = analysis.rows[analysis.rows['source_row_position'] == source_position]
    if matches.empty:
        return
    row = matches.iloc[0]
    supplier_text = customer_facing_value('supplier_text_raw', row['supplier_text_raw'])
    st.subheader(STATUS_LABELS[row['supplier_match_status']])
    colors = {'STRONG_MATCH': 'green', 'AMBIGUOUS_MATCH': 'yellow',
              'NO_MATCH': 'orange', 'SUPPLIER_NOT_IDENTIFIED': 'gray'}
    st.badge(STATUS_LABELS[row['supplier_match_status']], color=colors[row['supplier_match_status']])
    st.caption(SUPPLIER_MATCH_EXPLANATION)
    if row['supplier_match_status'] == 'STRONG_MATCH':
        st.caption('En stark namnmatchning har identifierats i avtalsregistret. '
                   'Detta bedömer inte fakturans riktighet eller om köpet omfattas av avtal.')
    elif row['supplier_match_status'] == 'NO_MATCH':
        st.text('Sökt leverantörsnamn: ' + str(supplier_text))
    elif row['supplier_match_status'] == 'AMBIGUOUS_MATCH':
        st.warning('Manuell granskning krävs. Jämför kandidaterna och matchningsorsakerna nedan; '
                   'ingen leverantör har valts automatiskt.')
    if row['registry_date_warning']:
        st.badge('Registerdatumvarning', color='violet')
    if row['registry_date_message']:
        st.warning(row['registry_date_message'])
    else:
        st.caption('Ingen registerdatumvarning: transaktionen är inte senare än registerutdraget.')
    candidates = analysis.candidates[analysis.candidates['source_row_position'] == source_position]
    show_supplier_candidates(matches, candidates)
    contracts = analysis.contracts[analysis.contracts['source_row_position'] == source_position]
    if not contracts.empty:
        with st.expander('Möjliga avtal – inget avtal har valts automatiskt'):
            st.caption('Alla registerposter visas med originaldatum, använd period, verifikationsdatum '
                       'och kontrollresultat. Osäker namnmatchning eller oklara datum ger NOT_CHECKED. '
                       'Vilket avtal köpet omfattas av har inte avgjorts.')
            st.dataframe(display_dataframe(contracts.drop(columns='source_row_position')),
                         hide_index=True, width='stretch', column_config={
                             **REGISTRY_ORGANIZATION_COLUMNS,
                             'contract_id': 'Avtals-ID', 'contract_name': 'Avtalsnamn',
                             'start_date': 'Startdatum (original)', 'end_date': 'Slutdatum (original)',
                             'final_end_date': 'Sista slutdatum (original)',
                             'verification_date': 'Verifikationsdatum (original)',
                             'evaluated_start_date': 'Använd period från', 'evaluated_end_date': 'Använd period till',
                             'contract_period_result': 'Avtalsperiod vid verifikationsdatum',
                             'contract_period_reason': 'Motivering',
                         })
