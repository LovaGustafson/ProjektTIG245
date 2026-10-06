"""Session-local chart navigation over completed analysis; no population rules."""
from collections.abc import Mapping

import streamlit as st


CHARTS = ('chart_population', 'chart_exclusions', 'chart_suppliers', 'chart_contracts', 'chart_sample')
RESULT_KEY = 'overview_charts:result'
REVISIONS_KEY = 'overview_charts:revisions'


def selected_category(event, categories):
    """Accept one existing backend key, never a label, count or row number."""
    if not isinstance(event, Mapping):
        return None
    selection = event.get('selection')
    if not isinstance(selection, Mapping):
        return None
    points = selection.get('category')
    if not isinstance(points, list) or len(points) != 1 or not isinstance(points[0], Mapping):
        return None
    category = points[0].get('Status')
    return category if isinstance(category, str) and category in categories else None


def reset_chart_selections(chart=None):
    """Remount widgets instead of assigning Streamlit's read-only selection state."""
    revisions = dict(st.session_state.get(REVISIONS_KEY, {}))
    for name in CHARTS if chart is None else (chart,):
        revisions[name] = revisions.get(name, 0) + 1
    st.session_state[REVISIONS_KEY] = revisions
    if chart is None:
        st.session_state.pop(RESULT_KEY, None)


def prepare_chart_selections(result):
    """A new completed result resets all charts, even with identical counts/keys.

    Keep a reference to the session's existing result (no copy or reanalysis).
    Identity avoids hashing source data and detects refiltering/register changes.
    """
    if st.session_state.get(RESULT_KEY) is not result:
        reset_chart_selections()
        st.session_state[RESULT_KEY] = result


def chart_widget_key(chart):
    revision = st.session_state.get(REVISIONS_KEY, {}).get(chart, 0)
    return f'overview_chart:{chart}:event:{revision}'
