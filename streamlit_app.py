"""Local invoice review interface. Run with streamlit run streamlit_app.py."""
import streamlit as st

from src.presentation import check_message, summary_counts
from src.ui_support import analyze_upload, flagged_table, validation_table


def clear_result():
    st.session_state.pop('review', None)
    st.session_state.pop('selected_verification', None)


def show_result(review):
    result = review.result
    flagged = flagged_table(result)
    errors = validation_table(result)
    a, b, c, d = st.columns(4)
    a.metric('Analyserade verifikationer', len(result.detection_results))
    b.metric('Flaggade verifikationer', len(flagged))
    c.metric('Valideringsfel', len(errors))
    d.metric('Kontroller som inte kunde genomföras (NOT_CHECKED)',
             summary_counts(result.standardized_data, result.validation, result.detection_results)['not_checked_results'])
    st.caption('Varje radfel räknas separat. Filfel räknas en gång. Radpositioner börjar på noll.')
    if any(check.status == 'NOT_CHECKED' for r in result.detection_results for check in r.checks):
        st.warning('Vissa kontroller är NOT_CHECKED i väntan på bekräftade förutsättningar. Avsaknad av flaggor betyder inte att alla kontroller är godkända.')
    if any(check.status == 'ERROR' for r in result.detection_results for check in r.checks):
        st.warning('Vissa kontroller avbröts med tekniska fel. Se kontrollresultaten nedan.')
    st.subheader('Flaggade verifikationer')
    st.dataframe(flagged.drop(columns='reasons'), hide_index=True)
    flagged_results = [r for r in result.detection_results if r.flag_reasons]
    if flagged_results:
        selected = st.selectbox('Välj en flaggad verifikation', range(len(flagged_results)),
                                format_func=lambda i: str(flagged_results[i].verification_id),
                                key='selected_verification')
        detection = flagged_results[selected]
        for check in detection.checks:
            if check.status == 'FLAGGED':
                st.text(check_message(check))
        for verification in result.verifications:
            if verification.verification_id == detection.verification_id:
                st.dataframe(verification.rows.astype(str), hide_index=True)
    else:
        st.info('Inga verifikationer har flaggats.')
    with st.expander('Valideringsfel'):
        st.caption('Filfel gäller filens struktur och saknar verifikationsnummer.')
        st.dataframe(errors[errors['scope'] == 'Fil'], hide_index=True)
        st.caption('Radfel visas med tillgängligt verifikationsnummer och radnummer.')
        st.dataframe(errors[errors['scope'] == 'Rad'], hide_index=True)
    with st.expander('Alla kontrollresultat'):
        for detection in result.detection_results:
            for check in detection.checks:
                st.text(f'{detection.verification_id} | {check.check_type} | {check.status}: {check_message(check)}')
    st.subheader('Ladda ner rapporter')
    for filename, content in review.downloads.items():
        st.download_button(filename, content, file_name=filename,
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def main():
    st.set_page_config(page_title='Fakturagranskning', layout='wide')
    st.title('Fakturagranskning')
    st.caption('Ladda upp en lokal .xlsx-fil. Det första kalkylbladet analyseras med projektets inställningar.')
    upload = st.file_uploader('Excel-fil', type=['xlsx'], on_change=clear_result)
    if st.button('Starta analys', disabled=upload is None):
        clear_result()
        try:
            with st.spinner('Analyserar verifikationer…'):
                st.session_state['review'] = analyze_upload(upload.getvalue())
        except Exception as exc:
            st.error('Analysen kunde inte slutföras. Kontrollera Excel-filen och projektets inställningar och försök igen.')
            st.text(f'Teknisk feltyp: {type(exc).__name__}.')
    if 'review' in st.session_state:
        show_result(st.session_state['review'])


if __name__ == '__main__':
    main()
