"""Local invoice review interface. Run with streamlit run streamlit_app.py."""
import streamlit as st

from src.ui_support import analyze_upload, flagged_table, validation_table


def clear_result():
    st.session_state.pop('review', None)
    st.session_state.pop('selected_verification', None)


def show_result(review):
    result = review.result
    flagged = flagged_table(result)
    errors = validation_table(result)
    a, b, c = st.columns(3)
    a.metric('Analyzed verifications', len(result.detection_results))
    b.metric('Flagged verifications', len(flagged))
    c.metric('Validation/data errors', len(errors))
    st.caption('Data errors count individual row errors plus schema errors once. Row positions are zero-based.')
    if any(check.status == 'NOT_CHECKED' for r in result.detection_results for check in r.checks):
        st.warning('Some checks remain NOT_CHECKED pending business confirmation. No flags does not mean all checks passed.')
    if any(check.status == 'ERROR' for r in result.detection_results for check in r.checks):
        st.warning('Some checks could not complete. See check results below.')
    st.subheader('Flagged verifications')
    st.dataframe(flagged, hide_index=True)
    flagged_results = [r for r in result.detection_results if r.flag_reasons]
    if flagged_results:
        selected = st.selectbox('Select a flagged verification', range(len(flagged_results)),
                                format_func=lambda i: str(flagged_results[i].verification_id),
                                key='selected_verification')
        detection = flagged_results[selected]
        for reason in detection.flag_reasons:
            st.text(reason)
        for verification in result.verifications:
            if verification.verification_id == detection.verification_id:
                st.dataframe(verification.rows.astype(str), hide_index=True)
    else:
        st.info('No verifications were flagged.')
    with st.expander('Validation errors'):
        st.dataframe(errors.astype(str), hide_index=True)
    with st.expander('All check results'):
        for detection in result.detection_results:
            for check in detection.checks:
                st.text(f'{detection.verification_id} | {check.check_type} | {check.status}: {check.reason}')
    st.subheader('Download reports')
    for filename, content in review.downloads.items():
        st.download_button(filename, content, file_name=filename,
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def main():
    st.set_page_config(page_title='Invoice review', layout='wide')
    st.title('Invoice review')
    st.caption('Upload a local .xlsx workbook. The first worksheet is analyzed using the project settings.')
    upload = st.file_uploader('Excel file', type=['xlsx'], on_change=clear_result)
    if st.button('Start analysis', disabled=upload is None):
        clear_result()
        try:
            with st.spinner('Analyzing verifications…'):
                st.session_state['review'] = analyze_upload(upload.getvalue())
        except Exception as exc:
            st.error('Analysis could not finish. Check the workbook and project settings, then try again.')
            st.text(f'{type(exc).__name__}: {exc}')
    if 'review' in st.session_state:
        show_result(st.session_state['review'])


if __name__ == '__main__':
    main()
