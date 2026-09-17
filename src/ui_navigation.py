"""Session-only navigation; never changes analysis or export data."""
import streamlit as st

from src.ui_filter_panel import clear_ui_filters

SELECTIONS = ('selected_kpi', 'selected_supplier', 'selected_control')


def home():
    clear_ui_filters()
    for key in (*SELECTIONS, 'review_rows', 'kpi_review_rows', 'selected_verification'):
        st.session_state.pop(key, None)


def select_drilldown(group, key, view=None):
    for selection in SELECTIONS:
        st.session_state.pop(selection, None)
    for selection in ('review_rows', 'kpi_review_rows'):
        st.session_state.pop(selection, None)
    if view:
        clear_ui_filters(view)
    st.session_state[group] = key


def active_drilldown(label, key):
    st.info('Aktivt vyfilter: ' + label)
    st.button('Rensa vyfilter', key='clear_drilldown_' + key, on_click=home)
