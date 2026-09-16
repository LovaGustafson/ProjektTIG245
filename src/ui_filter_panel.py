"""One reusable Streamlit panel for temporary, independently scoped view filters."""
from datetime import date

import streamlit as st

from src.ui_filters import ViewFilter, apply_filters, discover_filters


def clear_ui_filters(view=None, selection_key=None):
    prefix = 'vf:' if view is None else f'vf:{view}:'
    for key in list(st.session_state):
        if key.startswith(prefix):
            del st.session_state[key]
    if selection_key is not None:
        st.session_state.pop(selection_key, None)


def filter_panel(data, *, view, selection_key=None):
    """Return a filtered copy and original positional mapping for this view only."""
    prefix = f'vf:{view}:'
    definitions = discover_filters(data)
    labels = {definition.position: definition.label for definition in definitions}
    rules = {}
    with st.expander('Tillfälliga vyfilter'):
        st.caption('Gäller bara denna tabell. Regelklassning, KPI-antal och exporter påverkas inte. '
                   'Filter för olika kolumner kombineras med OCH.')
        st.button('Rensa alla filter', key=prefix + 'clear',
                  on_click=clear_ui_filters, args=(view, selection_key))
        selected = st.multiselect('Filtrera kolumner', list(labels), format_func=labels.get,
                                  key=prefix + 'columns', persist_state='session',
                                  placeholder='Välj en eller flera kolumner')
        for definition in definitions:
            if definition.position not in selected:
                continue
            key = prefix + f'c{definition.position}:'
            label = definition.label
            values = {}
            with st.container(border=True):
                st.write(label)
                # Public persistence keeps a KPI view's filters when another card is opened.
                common = dict(persist_state='session')
                if definition.kind == 'category':
                    values['categories'] = tuple(st.multiselect(
                        f'{label} – välj värden', definition.choices, key=key + 'categories', **common))
                if definition.kind in ('category', 'text'):
                    values['text'] = st.text_input(f'Sök i {label}', key=key + 'text', **common)
                if definition.kind == 'presence':
                    image = label.strip() in ('Bild', 'image_reference')
                    options = {'all': 'Alla', 'present': 'Bild finns' if image else 'Finns',
                               'missing': 'Ingen bild' if image else 'Saknas'}
                    values['presence'] = st.selectbox(label, list(options), format_func=options.get,
                                                      key=key + 'presence', **common)
                    st.caption('Visningstolkning: tomt, 0, false/nej/no, none/null/nan/n/a, '
                               '”saknas” och ”ingen bild” räknas som avsaknad. Övrig text och '
                               'ändliga tal utom 0 räknas som information. '
                               'Kontrollerar inte att en bilaga finns eller att en attest är giltig.')
                if definition.kind == 'date':
                    left, right = st.columns(2)
                    values['start'] = left.date_input('Från datum', value=None, min_value=date.min,
                                                      max_value=date.max, format='YYYY-MM-DD',
                                                      key=key + 'start', **common)
                    values['end'] = right.date_input('Till datum', value=None, min_value=date.min,
                                                     max_value=date.max, format='YYYY-MM-DD',
                                                     key=key + 'end', **common)
                    st.caption('Excel-datum, ISO-format och dag/månad/år stöds. '
                               'Tomma eller ogiltiga datum matchar inte ett aktivt intervall.')
                if definition.kind == 'number':
                    left, right = st.columns(2)
                    values['minimum'] = left.number_input('Min belopp', value=None, step=0.01,
                                                          key=key + 'minimum', **common)
                    values['maximum'] = right.number_input('Max belopp', value=None, step=0.01,
                                                           key=key + 'maximum', **common)
                    signs = {'all': 'Alla belopp', 'positive': 'Endast positiva',
                             'negative': 'Endast negativa', 'zero': 'Nollbelopp'}
                    values['sign'] = st.selectbox('Beloppstyp', list(signs), format_func=signs.get,
                                                  key=key + 'sign', **common)
                missing = {'all': 'Alla', 'present': 'Har värde', 'missing': 'Saknar värde'}
                values['missing'] = st.selectbox(f'{label} – tomma värden', list(missing),
                                                 format_func=missing.get, key=key + 'missing', **common)
                rules[definition.position] = ViewFilter(**values)
    filtered = apply_filters(data, rules)
    st.caption(f'Visar {len(filtered.data)} av {len(data)} rader')
    st.caption('Aktiva vyfilter: ' + (' · '.join(filtered.active) if filtered.active else 'Inga'))
    for notice in filtered.notices:
        st.caption(notice)
    if selection_key is not None:
        # Never keep a row selection pointing to a different row after filtering.
        previous = st.session_state.get(prefix + 'positions')
        if previous is not None and previous != filtered.positions:
            st.session_state.pop(selection_key, None)
        st.session_state[prefix + 'positions'] = filtered.positions
    return filtered
