"""Local invoice review interface. Run with streamlit run streamlit_app.py."""
from pathlib import Path

import streamlit as st
import pandas as pd

from src.filtering.filter_engine import load_exclusions, normalize_type, filter_column_errors
from src.output.report_generator import review_tables, review_summary
from src.presentation import SOURCE_NAMES, check_message
from src.ui_support import analyze_upload, flagged_table, validation_table, display_dataframe
from src.ui_support import filter_details, review_row_detail, REVIEW_EXPLANATION
from src.ui_filter_panel import filter_panel, clear_ui_filters
from src.ui_supplier_panel import show_supplier_summary, supplier_review_table, show_supplier_detail
from src.ui_supplier_panel import supplier_positions, SUPPLIER_VIEWS
from src.ui_navigation import home, select_drilldown, active_drilldown
from src.supplier_matching.settings import load_matching_settings, snapshot_date
from src.ui_run_summary import show_run_summary
from src.ingestion.registry_source import default_registry_location


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
    'uncertain_suppliers.xlsx': (
        'Osäkra leverantörsträffar',
        'Alla kvarvarande rader utan säker leverantörsträff, inklusive ej genomförbar matchning.',
        'Hämta osäkra leverantörsträffar', 'secondary',
    ),
}


def clear_result():
    home()
    st.session_state.pop('review', None)
    st.session_state.pop('excluded_types', None)


def change_registry(enabled, reset_upload=False):
    st.session_state['registry_enabled'] = enabled
    if reset_upload:
        st.session_state['registry_upload_version'] = st.session_state.get('registry_upload_version', 0) + 1
    clear_result()


def show_overview(result, flagged, errors):
    st.subheader('Kontrollresultat och förklaringar')
    st.caption('En samlad bild av det analyserade underlaget.')
    checks = pd.DataFrame([
        {'Verifikation': str(detection.verification_id),
         'Kontroll': CHECK_LABELS.get(check.check_type, check.check_type),
         'Status': STATUS_LABELS.get(check.status, check.status),
         'Beskrivning': check_message(check)}
        for detection in result.detection_results for check in detection.checks
    ], columns=['Verifikation', 'Kontroll', 'Status', 'Beskrivning'])
    # Each card and its table use the same record set and unit (not invoice rows).
    analyzed = pd.DataFrame([
        {'Verifikation': str(detection.verification_id),
         'Antal rader': len(verification.rows)}
        for detection, verification in zip(result.detection_results, result.verifications)
    ], columns=['Verifikation', 'Antal rader'])
    views = {
        'analyzed': ('Analyserade', analyzed, 'verifikationer'),
        'flagged': ('Flaggade', flagged, 'verifikationer'),
        'validation': ('Valideringsfel', errors, 'valideringsfel'),
        'not_checked': ('Ej kontrollerade', checks[checks['Status'] == 'Ej kontrollerad'], 'kontroller'),
    }
    with st.container(key='kpi_grid'):
        for column, (key, (label, data, unit)) in zip(st.columns(4), views.items()):
            column.button(f'**{len(data)}**  \n{label}', key='control_' + key, width='stretch',
                          help=f'Visa {unit}', on_click=select_drilldown,
                          args=('selected_control', key, 'control_' + key))
    selected = st.session_state.get('selected_control')
    if selected in views:
        label, data, unit = views[selected]
        active_drilldown(f'{label} ({unit})', 'control')
        show_filtered_table(data, view='control_' + selected)
    with st.expander('Alla kontrollresultat'):
        st.caption('Varje genomförd, ej genomförd eller avbruten kontroll visas med sin förklaring.')
        if not checks.empty:
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
    with st.expander('Avvikelser, manuellt stickprov och osäkra leverantörsträffar', expanded=True):
        st.caption('Stickprovet väljs efter analysen och begränsar inte vilka rader som granskas.')
        for filename in ('flagged_invoices.xlsx', 'manual_sample.xlsx', 'uncertain_suppliers.xlsx'):
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
    for message in result.filtering.todos:
        if message not in filter_column_errors(result.standardized_data):
            st.warning(message)
    show_run_summary(result)
    if result.supplier_analysis is not None:
        registry = result.supplier_analysis.registry
        st.text('Register för denna körning: ' + (registry.source_name or 'Inget register') +
                (' (matchning tillgänglig)' if registry.available else ' (matchning ej tillgänglig)'))
    st.divider()
    st.subheader('Detaljer och granskning')
    show_dashboard_kpis(result)
    review_tab, excluded_tab, controls, reports, manual = st.tabs(
        ['Granskning', 'Bortfiltrerade', 'Kontroller', 'Export', 'Manuell kontroll'])
    kept, excluded = review_tables(result.original_data, result.filtering)
    with review_tab:
        show_supplier_summary(result.supplier_analysis)
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
        if result.supplier_analysis is None or not result.supplier_analysis.registry.available:
            st.info('Upphandlingskontroll – ej tillgänglig. Upphandlingsregister saknas.')
        else:
            st.info('Leverantörsmatchning och separata avtalsperioder visas under Granskning. Avtalstrohet har inte kontrollerats; '
                    'vilket avtal fakturan avser behöver utredas.')
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
    view = 'kpi_review_rows' if key == 'review' else f'kpi_{key}'
    select_drilldown('selected_kpi', key, view)


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
        active_drilldown(list(counts)[keys.index(selected)], 'dashboard')
        if selected == 'total':
            st.write('Alla inlästa datarader visas här. Metadata-rader ovanför den identifierade '
                     'header-raden räknas inte, och header-raden räknas inte som en datarad. '
                     'Rapportfötter ingår i inlästa rader men räknas inte som transaktioner '
                     'eller kvar för granskning.')
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
    selected = st.session_state.get('selected_supplier') if key == 'review_rows' else None
    if selected and result.supplier_analysis and result.supplier_analysis.registry.available:
        analysis = result.supplier_analysis
        label = list(analysis.summary())[SUPPLIER_VIEWS.index(selected)]
        active_drilldown(label, 'supplier')
        kept = kept.loc[kept.index.isin(supplier_positions(analysis, selected))]
    kept = supplier_review_table(kept, result.supplier_analysis)
    filtered = filter_panel(kept, view=key, selection_key=key)
    selection = st.dataframe(display_dataframe(filtered.data), hide_index=True, width='stretch',
                             key=key, on_select='rerun', selection_mode='single-row')
    st.caption('Markera en rad i tabellen för att visa källvärden och valideringsvarningar.')
    if selection.selection.rows and selection.selection.rows[0] < len(filtered.positions):
        source_position = kept.index[filtered.positions[selection.selection.rows[0]]]
        show_review_row(result, result.filtering.cleaned_data.index.get_loc(source_position))


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
        source_position = result.filtering.cleaned_data.index[position]
        show_supplier_detail(result.supplier_analysis, source_position)
        st.caption('Alla tillgängliga originalfält visas oförändrade.')
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
        st.button('Till översikt', key='home', icon=':material/home:', on_click=home)
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
        updated = analyze_upload(review.source_content, excluded_verification_types=selected,
                                 registry_content=review.registry_content,
                                 registry_snapshot_date=review.registry_snapshot_date,
                                 registry_source=review.registry_source, source_name=review.source_name,
                                 settings_path=review.settings_path)
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
        registry_config = load_matching_settings()
        registry_upload = st.file_uploader('Byt koncerninköpsregister (valfritt)', type=['xlsx'],
            key=f'registry_upload_{st.session_state.get("registry_upload_version", 0)}',
            on_change=change_registry, args=(True,))
        enabled = st.session_state.get('registry_enabled', True)
        if not enabled:
            st.caption('Avtalsregister avaktiverat. Ingen leverantörsmatchning genomförs.')
        elif registry_upload:
            st.text(f'Aktivt avtalsregister: {registry_upload.name} (eget register ersätter standardregistret)')
        else:
            default_path, label = default_registry_location(registry_config)
            st.text(f'Förvalt avtalsregister: {label}')
            if not default_path or not default_path.is_file():
                st.info('Standardregisterfilen saknas. Ladda upp ett register för att genomföra leverantörsmatchning.')
        registry_date = st.date_input('Registerutdragets datum',
            value=snapshot_date(registry_config['registry_snapshot_date']) if registry_config.get('registry_snapshot_date') else None,
            on_change=clear_result,
            help='Används för att varna när transaktionen är senare än registerutdraget.')
        start = st.button('Starta analys', disabled=upload is None, type='primary')
        st.button('Ta bort register', on_click=change_registry, args=(False,), disabled=not enabled)
        st.button('Återställ standardregister', on_click=change_registry, args=(True, True))
    if start:
        clear_result()
        try:
            with st.spinner('Analyserar samtliga rader…'):
                st.session_state['review'] = analyze_upload(upload.getvalue(),
                    registry_content=registry_upload.getvalue() if registry_upload else None,
                    registry_snapshot_date=registry_date,
                    registry_mode='default' if enabled else 'disabled',
                    registry_name=registry_upload.name if registry_upload else None,
                    source_name=upload.name)
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
