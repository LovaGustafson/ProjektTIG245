"""Local invoice review interface. Run with streamlit run streamlit_app.py."""
from pathlib import Path

import streamlit as st
import pandas as pd

from src.filtering.filter_engine import load_exclusions, normalize_type, filter_column_errors
from src.output.report_generator import review_tables, review_summary
from src.presentation import SOURCE_NAMES, check_message, summary_counts
from src.ui_support import analyze_upload, flagged_table, validation_table, display_dataframe
from src.ui_support import filter_details, review_row_detail, REVIEW_EXPLANATION
from src.ui_filter_panel import filter_panel, clear_ui_filters


# Display labels only. Original values and report contents are left intact.
STATUS_LABELS = {
    'PASS': 'Utan anmärkning', 'FLAGGED': 'Flaggad',
    'ERROR': 'Tekniskt fel', 'NOT_CHECKED': 'Ej kontrollerad',
}
CHECK_LABELS = {
    'required_fields_check': 'Obligatoriska uppgifter',
    'image_check': 'Fakturabild', 'supplier_check': 'Leverantör',
    'attestation_check': 'Attest',
}
COLUMN_LABELS = {
    **SOURCE_NAMES,
    'verification_id': 'Verifikation', 'verification_line_id': 'Verifikationsrad',
    'verification_date': 'Datum', 'header_text': 'Huvudtext',
    'amount': 'Belopp', 'account': 'Konto', 'status': 'Status',
    'field': 'Uppgift', 'message': 'Beskrivning', 'code': 'Felkod',
    'row_position': 'Position (från 0)',
}
REPORT_LABELS = {
    'cleaned_data.xlsx': (
        'Rensat underlag',
        'Raderna som återstår efter filtrering. Underlaget kan fortfarande innehålla valideringsfel.',
        'Hämta rensat underlag', 'secondary',
    ),
    'flagged_invoices.xlsx': (
        'Flaggade verifikationer',
        'Flaggningsorsaker, tillhörande verifikationsrader och en sammanfattning av analysen.',
        'Hämta avvikelserapport', 'primary',
    ),
    'manual_sample.xlsx': (
        'Manuellt stickprov',
        'Verifikationsraderna i det stickprov som valts ut för manuell granskning.',
        'Hämta manuellt stickprov', 'secondary',
    ),
}


def clear_result():
    clear_ui_filters()
    st.session_state.pop('review_rows', None)
    st.session_state.pop('kpi_review_rows', None)
    st.session_state.pop('selected_kpi', None)
    st.session_state.pop('review', None)
    st.session_state.pop('selected_verification', None)
    st.session_state.pop('excluded_types', None)


def show_overview(result, flagged, errors):
    st.subheader('Analysöversikt')
    st.caption('En samlad bild av det analyserade underlaget.')
    with st.container(key='kpi_grid'):
        a, b, c, d = st.columns(4)
        a.metric('Analyserade', len(result.detection_results), border=True,
                 help='Antal analyserade verifikationer, inte antal Excel-rader.')
        b.metric('Flaggade', len(flagged), border=True,
                 help='Antal verifikationer med minst en flaggningsorsak.')
        c.metric('Valideringsfel', len(errors), border=True,
                 help='Varje radfel räknas separat. Filfel räknas en gång.')
        d.metric('Ej kontrollerade',
                 summary_counts(result.standardized_data, result.validation,
                                result.detection_results)['not_checked_results'],
                 border=True, help='Antal kontroller som inte kunde genomföras. Avser kontroller, inte verifikationer.')
    with st.expander('Alla kontrollresultat'):
        st.caption('Varje genomförd, ej genomförd eller avbruten kontroll visas med sin förklaring.')
        checks = [
            {'Verifikation': str(detection.verification_id),
             'Kontroll': CHECK_LABELS.get(check.check_type, check.check_type),
             'Status': STATUS_LABELS.get(check.status, check.status),
             'Beskrivning': check_message(check)}
            for detection in result.detection_results for check in detection.checks
        ]
        if checks:
            st.dataframe(display_dataframe(checks), hide_index=True, width='stretch')
        else:
            st.info('Det finns inga kontrollresultat att visa.')


def show_deviations(result, flagged):
    st.subheader('Flaggade verifikationer')
    st.caption('En verifikation kan omfatta flera rader och ha flera flaggningsorsaker.')
    flagged_results = [r for r in result.detection_results if r.flag_reasons]
    if not flagged_results:
        st.info('Inga verifikationer har flaggats. Granska även valideringsfel och ej genomförda kontroller.')
        return
    display = flagged.drop(columns='reasons').copy()
    display['status'] = display['status'].replace(STATUS_LABELS)
    st.dataframe(display_dataframe(display), column_config=COLUMN_LABELS, hide_index=True, width='stretch')
    with st.container(border=True, key='verification_detail'):
        selected = st.selectbox('Välj en flaggad verifikation', range(len(flagged_results)),
                                format_func=lambda i: str(flagged_results[i].verification_id),
                                key='selected_verification')
        detection = flagged_results[selected]
        st.badge('Flaggad verifikation', icon=':material/flag:', color='orange')
        st.markdown('#### Orsaker till flaggning')
        # Render source-derived text as text, never interpolate it into HTML.
        for check in detection.checks:
            if check.status == 'FLAGGED':
                st.text(check_message(check))
        st.markdown('#### Tillhörande verifikationsrader')
        st.caption('Samtliga rader för den valda verifikationen. Värdena visas utan ändringar.')
        for verification in result.verifications:
            if verification.verification_id == detection.verification_id:
                st.dataframe(display_dataframe(verification.rows), column_config=COLUMN_LABELS,
                             hide_index=True, width='stretch')


def show_validation(errors):
    st.subheader('Valideringsfel')
    st.caption('Problem i underlagets struktur och värden. Dessa visas separat från flaggningsorsaker.')
    for scope, title, explanation, columns in [
        ('Fil', 'Filens struktur', 'Gäller hela filen, till exempel saknade eller dubbla kolumner.',
         ['field', 'message', 'code']),
        ('Rad', 'Fel på enskilda rader', 'Visas med verifikationsnummer och verifikationsrad när uppgifterna finns.',
         ['verification_id', 'verification_line_id', 'field', 'message', 'row_position', 'code']),
    ]:
        with st.container(border=True):
            st.markdown(f'#### {title}')
            st.caption(explanation)
            subset = errors.loc[errors['scope'] == scope, columns].copy()
            if subset.empty:
                st.info('Inga filfel har rapporterats.' if scope == 'Fil' else 'Inga radfel har rapporterats.')
            else:
                subset['field'] = subset['field'].replace(SOURCE_NAMES)
                st.dataframe(display_dataframe(subset), column_config=COLUMN_LABELS, hide_index=True, width='stretch')
                if scope == 'Rad':
                    st.caption('Position räknas från 0 i underlaget och är inte Excel-filens radnummer.')


def show_reports(review):
    st.subheader('Exportera granskningsunderlag')
    st.caption('Varje nedladdning skapar en ny Excel-fil. Originalfilen förändras inte.')
    labels = {'granskning.xlsx': 'Kvar för granskning',
              'bortfiltrerade.xlsx': 'Bortfiltrerade',
              'samlad_kontrollfil.xlsx': 'Samlad kontrollfil'}
    for filename, label in labels.items():
        st.download_button(label, review.downloads[filename], file_name=filename,
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    with st.expander('Avvikelser och separat manuellt stickprov'):
        st.caption('Stickprovet väljs efter analysen och begränsar inte vilka rader som granskas.')
        for filename in ('flagged_invoices.xlsx', 'manual_sample.xlsx'):
            st.download_button(REPORT_LABELS[filename][2], review.downloads[filename],
                               file_name=filename,
                               mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def show_result(review):
    result = review.result
    flagged = flagged_table(result)
    errors = validation_table(result)
    st.success('Analysen är klar. Granska resultatet i flikarna nedan.', icon=':material/task_alt:')
    # Keep incomplete/failed-control notices visible regardless of the active tab.
    if any(check.status == 'NOT_CHECKED' for r in result.detection_results for check in r.checks):
        st.warning('Vissa kontroller kunde inte genomföras eftersom förutsättningarna ännu inte är bekräftade. '
                   'Avsaknad av flaggor betyder inte att alla kontroller är godkända.', icon=':material/info:')
    if any(check.status == 'ERROR' for r in result.detection_results for check in r.checks):
        st.warning('Vissa kontroller avbröts med tekniska fel. Se Alla kontrollresultat under Kontroller.',
                   icon=':material/warning:')
    for message in filter_column_errors(result.standardized_data):
        st.error(message)
    show_dashboard_kpis(result)
    review_tab, excluded_tab, controls, reports, manual = st.tabs(
        ['Granskning', 'Bortfiltrerade', 'Kontroller', 'Export', 'Manuell kontroll'])
    kept, excluded = review_tables(result.original_data, result.filtering)
    with review_tab:
        st.caption('Alla kvarvarande rader med ursprungliga kolumnnamn och värden. '
                   'Även rader med valideringsfel finns kvar för granskning.')
        show_review_table(result, kept, key='review_rows')
        show_deviations(result, flagged)
        with st.expander('Valideringsfel', expanded=not errors.empty):
            show_validation(errors)
    with excluded_tab:
        st.caption('Raderna finns kvar här med samtliga exkluderingsorsaker.')
        show_filtered_table(excluded, view='excluded')
    with controls:
        st.info('Upphandlingskontroll – ej tillgänglig. Upphandlingsregister saknas.')
        st.info('Attestkontroll – ej tillgänglig. Attestregister saknas.')
        st.info('Kontroll av rätt attestant – ej tillgänglig. Kräver attestregister. Framtida funktion.')
        show_overview(result, flagged, errors)
    with reports:
        show_reports(review)
    with manual:
        st.caption('Det befintliga manuella stickprovet, valt efter analysen. '
                   'Vyfiltren ändrar inte vilka verifikationer som ingår i stickprovet.')
        # The reader supplies unique row indexes; grouping/sampling retain them.
        positions = [position for verification in result.manual_sample for position in verification.rows.index]
        sample = result.original_data.loc[positions].copy(deep=True)
        show_filtered_table(sample, view='manual')


def select_kpi(key):
    if st.session_state.get('selected_kpi') != key:
        st.session_state.pop('kpi_review_rows', None)
    st.session_state['selected_kpi'] = key


def show_dashboard_kpis(result):
    counts = review_summary(result.original_data, result.filtering)
    keys = ['total', 'review', 'account', 'verification_type', 'excluded']
    with st.container(key='dashboard_kpis'):
        for column, key, (label, value) in zip(st.columns(5), keys, counts.items()):
            column.button(f'**{value}**  \n{label}', key=f'kpi_{key}', width='stretch',
                          help=f'Visa rader: {label}', on_click=select_kpi, args=(key,),
                          type='primary' if st.session_state.get('selected_kpi') == key else 'secondary')
    st.caption('Klicka på ett kort för att visa rader och förklaring. Antalen avser rader. '
               'En rad kan träffa både konto- och typregeln; '
               'totalt bortfiltrerade räknar varje rad en gång.')
    selected = st.session_state.get('selected_kpi')
    if selected not in keys:
        return
    with st.container(border=True, key='kpi_detail'):
        st.subheader(list(counts)[keys.index(selected)])
        if selected == 'total':
            st.write('Alla inlästa datarader visas här. Metadata-rader ovanför den identifierade '
                     'header-raden räknas inte, och header-raden räknas inte som en datarad.')
            show_filtered_table(result.original_data, view='kpi_total')
        elif selected == 'review':
            st.info(REVIEW_EXPLANATION)
            for message in filter_column_errors(result.standardized_data):
                st.warning(message)
            kept, _ = review_tables(result.original_data, result.filtering)
            show_review_table(result, kept, key='kpi_review_rows')
        elif selected in ('account', 'verification_type'):
            per_value, rows = filter_details(result, selected)
            st.caption('Aktiva exkluderingar och antal träffar per värde, inklusive värden utan träffar.')
            st.dataframe(display_dataframe(per_value), hide_index=True, width='stretch')
            st.caption('Samtliga rader som träffade denna regel, även de som träffade båda reglerna.')
            show_filtered_table(rows, view=f'kpi_{selected}')
        else:
            _, excluded = review_tables(result.original_data, result.filtering)
            st.write('Alla bortfiltrerade källrader visas en gång. Om en rad träffade både konto- '
                     'och verifikationstypsregeln visas båda exkluderingsorsakerna.')
            show_filtered_table(excluded, view='kpi_excluded')


def show_filtered_table(data, *, view):
    filtered = filter_panel(data, view=view)
    st.dataframe(display_dataframe(filtered.data), hide_index=True, width='stretch')


def show_review_table(result, kept, *, key):
    filtered = filter_panel(kept, view=key, selection_key=key)
    selection = st.dataframe(display_dataframe(filtered.data), hide_index=True, width='stretch',
                             key=key, on_select='rerun', selection_mode='single-row')
    st.caption('Markera en rad i tabellen för att visa källvärden och valideringsvarningar.')
    if selection.selection.rows:
        show_review_row(result, filtered.positions[selection.selection.rows[0]])


def show_review_row(result, position):
    fields, warnings = review_row_detail(result, position)
    with st.container(border=True):
        st.subheader('Vald rad – detaljer')
        st.info(REVIEW_EXPLANATION)
        for message in filter_column_errors(result.standardized_data):
            st.warning(message)
        for message in warnings:
            st.warning(message)
        if not warnings:
            st.caption('Inga valideringsvarningar har rapporterats för raden.')
        st.caption('Alla tillgängliga originalfält visas. Leverantörsidentifiering väntar på AK:s bekräftelse.')
        # Vertical text avoids truncating long source texts inside table cells.
        for name, value in fields.itertuples(index=False, name=None):
            st.text(str(name))
            st.text('—' if pd.isna(value) else str(value))


def show_filters(review):
    defaults = load_exclusions()['excluded_verification_types'] or []
    data = review.result.standardized_data
    present = (sorted({normalize_type(value) for value in data['verification_type']} - {''})
               if list(data.columns).count('verification_type') == 1 else [])
    options = sorted(set(defaults) | set(present))
    with st.sidebar:
        st.subheader('Exkluderingsregler (MoSCoW)')
        st.caption('Valda typer exkluderas. Ta bort ett val för att återinkludera typen.')
        if st.button('Återställ filter till standard'):
            st.session_state['excluded_types'] = defaults
        selected = st.multiselect('Exkluderade verifikationstyper', options,
                                  default=defaults, key='excluded_types')
        st.write('Aktiva typer i filen: ' + (', '.join(t for t in present if t not in selected) or 'Inga'))
        st.caption('Konto 7698 och 7699 exkluderas alltid. Tom Vertyp behålls.')
    previous = tuple(sorted(defaults)) if review.excluded_types is None else review.excluded_types
    if tuple(sorted(selected)) != previous:
        updated = analyze_upload(review.source_content, excluded_verification_types=selected)
        clear_ui_filters()
        st.session_state.pop('selected_verification', None)
        st.session_state.pop('review_rows', None)
        st.session_state.pop('kpi_review_rows', None)
        st.session_state['review'] = updated
        return updated
    return review


def main():
    st.set_page_config(page_title='Fakturagranskning', layout='wide')
    st.html(Path(__file__).parent / '.streamlit' / 'style.css')
    with st.container(key='page_header'):
        st.caption('UNDERLAG · ANALYS · GRANSKNING')
        st.title('Fakturagranskning')
        st.write('Granska leverantörsfakturor, förstå avvikelser och samla underlag för manuell kontroll.')
        st.html('<div class="audit-assurances"><span>Lokal analys</span>'
                '<span>Originaldata förändras inte</span></div>')
    with st.sidebar:
        st.subheader('Ladda upp underlag')
        st.caption('Excel (.xlsx), första kalkylbladet. Alla rader behandlas.')
        upload = st.file_uploader('Välj Excel-fil', type=['xlsx'], on_change=clear_result)
        start = st.button('Starta analys', disabled=upload is None, type='primary')
    if start:
        clear_result()
        try:
            with st.spinner('Analyserar samtliga rader…'):
                st.session_state['review'] = analyze_upload(upload.getvalue())
        except Exception:
            st.error('Analysen kunde inte slutföras. Kontrollera att filen är en giltig Excel-fil '
                     'och att projektets inställningar är korrekta.')
    if 'review' in st.session_state:
        try:
            review = show_filters(st.session_state['review'])
        except Exception:
            st.error('Filtren kunde inte uppdateras. Kontrollera filen och försök igen.')
            return
        show_result(review)
    elif not start:
        with st.container(border=True, key='empty_state'):
            st.subheader('Här börjar granskningen', icon=':material/fact_check:')
            st.write('När analysen är klar visas en översikt, eventuella avvikelser och valideringsfel. '
                     'Därefter kan du exportera granskningsunderlaget.')
            st.caption('Resultatet är ett stöd för granskning, inte ett godkännande av fakturorna.')


if __name__ == '__main__':
    main()
