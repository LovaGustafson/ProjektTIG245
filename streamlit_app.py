"""Local invoice review interface. Run with streamlit run streamlit_app.py."""
from pathlib import Path

import streamlit as st

from src.presentation import SOURCE_NAMES, check_message, summary_counts
from src.ui_support import analyze_upload, flagged_table, validation_table


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
    st.session_state.pop('review', None)
    st.session_state.pop('selected_verification', None)


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
    with st.container(border=True, key='overview_guide'):
        st.markdown('#### Fortsätt granskningen')
        st.markdown(
            '**Avvikelser** — se flaggade verifikationer och läs orsakerna.\n\n'
            '**Valideringsfel** — granska problem i filens struktur och på enskilda rader.\n\n'
            '**Rapporter** — hämta underlag, avvikelser och manuellt stickprov som Excel-filer.'
        )
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
            st.dataframe(checks, hide_index=True, width='stretch')
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
    st.dataframe(display, column_config=COLUMN_LABELS, hide_index=True, width='stretch')
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
                st.dataframe(verification.rows.astype(str), column_config=COLUMN_LABELS,
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
                st.dataframe(subset, column_config=COLUMN_LABELS, hide_index=True, width='stretch')
                if scope == 'Rad':
                    st.caption('Position räknas från 0 i underlaget och är inte Excel-filens radnummer.')


def show_reports(review):
    st.subheader('Hämta rapporter')
    st.caption('Tre Excel-rapporter från den aktuella analysen. Originalfilen förändras inte.')
    with st.container(key='report_grid'):
        columns = st.columns(3, gap='medium')
        for column, (filename, content) in zip(columns, review.downloads.items()):
            title, description, label, button_type = REPORT_LABELS[filename]
            with column, st.container(border=True, key=f'report_{Path(filename).stem}'):
                st.badge('Excel · .xlsx', color='gray', icon=':material/description:')
                st.markdown(f'#### {title}')
                with st.container(key=f'report_description_{Path(filename).stem}'):
                    st.write(description)
                st.caption(filename)
                st.download_button(label, content, file_name=filename,
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                   type=button_type, width='stretch', key=f'download_{filename}')
    st.caption('Valideringsdetaljer och alla kontrollresultat finns i gränssnittet. '
               'Rapporterna ersätter inte granskningen av dessa uppgifter.')


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
        st.warning('Vissa kontroller avbröts med tekniska fel. Se Alla kontrollresultat under Översikt.',
                   icon=':material/warning:')
    overview, deviations, validation, reports = st.tabs(['Översikt', 'Avvikelser', 'Valideringsfel', 'Rapporter'])
    with overview:
        show_overview(result, flagged, errors)
    with deviations:
        show_deviations(result, flagged)
    with validation:
        show_validation(errors)
    with reports:
        show_reports(review)


def main():
    st.set_page_config(page_title='Fakturagranskning', layout='wide')
    st.html(Path(__file__).parent / '.streamlit' / 'style.css')
    with st.container(key='page_header'):
        st.caption('UNDERLAG · ANALYS · GRANSKNING')
        st.title('Fakturagranskning')
        st.write('Granska leverantörsfakturor, förstå avvikelser och samla underlag för manuell kontroll.')
        st.html('<div class="audit-assurances"><span>Lokal analys</span>'
                '<span>Originaldata förändras inte</span></div>')
    st.html('''<ol class="audit-steps" aria-label="Granskningsflöde">
        <li><span>1</span> Ladda upp underlag</li><li><span>2</span> Starta analys</li>
        <li><span>3</span> Se analysöversikt</li><li><span>4</span> Granska avvikelser</li>
        <li><span>5</span> Granska valideringsfel</li><li><span>6</span> Hämta rapporter</li>
        </ol>''')
    with st.container(border=True, key='upload_card'):
        upload_area, action_area = st.columns([2, 1], gap='large', vertical_alignment='center')
        with upload_area:
            st.subheader('1. Ladda upp underlag')
            st.caption('Välj en Excel-fil (.xlsx). Det första kalkylbladet används.')
            upload = st.file_uploader('Välj Excel-fil', type=['xlsx'], on_change=clear_result)
        with action_area:
            st.subheader('2. Starta analys')
            st.write('Analysera underlaget och gå vidare till granskning och rapporter.')
            start = st.button('Starta analys', disabled=upload is None, type='primary',
                              width='stretch', icon=':material/play_arrow:')
            st.caption('Välj en fil för att aktivera analysen.' if upload is None else 'Filen är vald. Du kan starta analysen.')
        if start:
            clear_result()
            try:
                with st.spinner('Analyserar verifikationer…'):
                    st.session_state['review'] = analyze_upload(upload.getvalue())
            except Exception as exc:
                st.error('Analysen kunde inte slutföras. Kontrollera Excel-filen och projektets inställningar och försök igen.',
                         icon=':material/error:')
                with st.expander('Teknisk information'):
                    st.text(f'Teknisk feltyp: {type(exc).__name__}.')
    if 'review' in st.session_state:
        show_result(st.session_state['review'])
    elif not start:
        with st.container(border=True, key='empty_state'):
            st.subheader('Här börjar granskningen', icon=':material/fact_check:')
            st.write('När analysen är klar visas en översikt, eventuella avvikelser och valideringsfel. '
                     'Därefter kan du hämta de tre rapporterna.')
            st.caption('Resultatet är ett stöd för granskning, inte ett godkännande av fakturorna.')


if __name__ == '__main__':
    main()
