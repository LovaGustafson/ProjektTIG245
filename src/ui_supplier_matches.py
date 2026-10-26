"""Progressive disclosure of existing supplier evidence, shared by review views."""
import pandas as pd
import streamlit as st

from src.presentation import REGISTRY_ORGANIZATION_COLUMNS
from src.ui_overview_details import supplier_candidate_comparisons
from src.ui_support import display_dataframe

MATCH_LABELS = {
    'STRONG_MATCH': 'Stark namnmatchning',
    'AMBIGUOUS_MATCH': 'Osäker namnmatchning',
    'NO_MATCH': 'Ingen träff i registret',
    'SUPPLIER_NOT_IDENTIFIED': 'Leverantör ej identifierad',
}
SCORE_EXPLANATION = (
    'Matchningsscore är ett tekniskt mått på namnlikhet på skalan 0–1, inte sannolikheten '
    'att det är rätt juridisk leverantör. Matchningsresultatet gäller källraden och score '
    'gäller respektive kandidat. Hög score kan förekomma vid osäker namnmatchning.'
)
SIMPLE_COLUMNS = ['supplier_text_raw', 'supplier_name', 'match_result', 'score', 'explanation']


def readable_reason(reason, method):
    """Translate recorded clauses, retaining unknown reasons rather than guessing."""
    if not isinstance(reason, str):
        return 'Förklaring saknas i underlaget.'
    clauses = {
        'exact_normalized': [('Exakt normaliserat namn.',
                              'Leverantörsnamnen överensstämmer efter standardisering.')],
        'prefix': [('Namnet är ett prefix av registernamnet.',
                    'Leverantörsnamnen har en gemensam början.')],
        'uncertain_prefix': [('Namnet är ett prefix av registernamnet.',
                              'Leverantörsnamnen har en gemensam början.')],
        'fuzzy': [('Hög teckenlikhet med samma antal namnord.',
                   'Leverantörsnamnen är mycket lika och har samma antal ord.')],
    }
    for old, new in clauses.get(method, []):
        reason = reason.replace(old, new)
    for old, new in [
        ('Stark namnmatchning i avtalsregistret. ', ''),
        ('Flera eller osäkra namnmatchningar – kontrollera manuellt. ',
         'Namnmatchningen är osäker och behöver granskas manuellt. '),
        ('Liknande namn, men otillräcklig säkerhet eller avvikande namnord.',
         'Leverantörsnamnen liknar varandra, men likheten räcker inte för en stark namnmatchning '
         'eller så skiljer sig orden i namnen.'),
        ('Prefixet uppfyller inte säkerhetskraven.',
         'Den gemensamma början räcker inte för en stark namnmatchning.'),
        ('Namnet innehåller redan en fullständig bolagsform före ytterligare namntext.',
         'Bolagsformen följs av ytterligare text i registernamnet.'),
        ('Bolagsformen kan inte bekräftas.', 'Bolagsformen i namnen kan inte bekräftas som samma.'),
        ('Organisationsnummer saknas i registret.',
         'Organisationsnummer saknas i avtalsregistret, vilket hindrar en stark namnmatchning.'),
        # The recorded clause never contains the register value; keep it that way here.
        ('Organisationsnumret i registret är inte ett tekniskt giltigt organisationsnummer.',
         'Organisationsnumret i avtalsregistret är inte ett giltigt svenskt organisationsnummer, '
         'vilket hindrar en stark namnmatchning. Numret kan vara felskrivet, ofullständigt '
         'eller ha ett annat format.'),
    ]:
        reason = reason.replace(old, new)
    return reason


def _is_selected_candidate(row, candidate):
    """Match the recorded organization identity, not a displayed name or score."""
    return (row['supplier_match_status'] == 'STRONG_MATCH'
            and pd.notna(row['matched_organization_number'])
            and pd.notna(candidate['organization_number'])
            and candidate['organization_number'] == row['matched_organization_number'])


def match_explanation(row, candidate=None):
    """Describe the engine's row decision separately from a candidate's similarity."""
    reason = readable_reason(row['supplier_match_reason'], row['supplier_match_method'])
    if (candidate is not None and row['supplier_match_status'] == 'STRONG_MATCH'
            and not _is_selected_candidate(row, candidate)):
        return ('Alternativ kandidat – inte vald. Avtalsperioden har inte bedömts för denna identitet. '
                + readable_reason(candidate['reason'], candidate['method']))
    if row['supplier_match_status'] == 'AMBIGUOUS_MATCH' and row['candidate_count'] > 1:
        recorded = f"{row['candidate_count']} möjliga registerkandidater; ingen har valts."
        reason = reason.replace(recorded,
            'Flera möjliga leverantörer hittades. Systemet kan inte säkert avgöra vilken som är rätt.')
        if candidate is not None:
            reason += ' ' + readable_reason(candidate['reason'], candidate['method'])
    return reason


def candidate_summary(row):
    count = row['candidate_count']
    if pd.isna(count):
        return 'Antalet möjliga leverantörer saknas i underlaget.'
    if count == 0:
        if row['supplier_match_status'] == 'SUPPLIER_NOT_IDENTIFIED':
            return 'Inget leverantörsnamn kunde extraheras; ingen namnmatchning kunde göras.'
        return 'Ingen möjlig leverantör hittades.'
    if count == 1:
        return '1 möjlig leverantör hittades.'
    if row['supplier_match_status'] == 'STRONG_MATCH':
        return (f'{int(count)} möjliga leverantörer hittades – en har valts genom exakt namnmatchning; '
                'övriga är alternativa kandidater.')
    return f'{int(count)} möjliga leverantörer hittades – kontrollera vilken som är rätt.'


def simple_match_rows(matches, candidates):
    """One display row per candidate; unmatched source rows remain visible too."""
    linked = supplier_candidate_comparisons(matches, candidates)
    evidence = matches.set_index('source_row_position')
    records = []
    for candidate in linked.to_dict('records'):
        row = evidence.loc[candidate['source_row_position']]
        label = MATCH_LABELS.get(row['supplier_match_status'], 'Okänt matchningsresultat')
        if row['supplier_match_status'] == 'STRONG_MATCH' and not _is_selected_candidate(row, candidate):
            label = 'Alternativ kandidat – inte vald'
        records.append({
            'supplier_text_raw': row['supplier_text_raw'], 'supplier_name': candidate['supplier_name'],
            'match_result': label,
            'score': candidate['score'], 'explanation': match_explanation(row, candidate),
        })
    for row in matches.loc[~matches.source_row_position.isin(candidates.source_row_position)].to_dict('records'):
        records.append({
            'supplier_text_raw': row['supplier_text_raw'], 'supplier_name': 'Ingen kandidat tillgänglig',
            'match_result': MATCH_LABELS.get(row['supplier_match_status'], 'Okänt matchningsresultat'),
            'score': None, 'explanation': match_explanation(row),
        })
    display = pd.DataFrame(records, columns=SIMPLE_COLUMNS)
    display['supplier_text_raw'] = display['supplier_text_raw'].map(
        lambda name: name if pd.notna(name) and str(name).strip() else 'Inget extraherat leverantörsnamn')
    return display


def show_supplier_candidates(matches, candidates):
    st.markdown('**Befintliga leverantörskandidater och matchningsorsaker**')
    if matches.empty and candidates.empty:
        st.caption('Inga poster i denna kategori.')
        return
    st.caption(SCORE_EXPLANATION)
    if len(matches) == 1:
        st.caption(candidate_summary(matches.iloc[0]))
    st.dataframe(display_dataframe(simple_match_rows(matches, candidates)), hide_index=True, width='stretch',
                 column_order=SIMPLE_COLUMNS, column_config={
                     'supplier_text_raw': st.column_config.TextColumn('Leverantör i internkontrollsfilen', width='large'),
                     'supplier_name': st.column_config.TextColumn('Leverantör i avtalsregistret', width='large'),
                     'match_result': 'Matchningsresultat',
                     'score': st.column_config.NumberColumn('Matchningsscore', format='%.6f', help=SCORE_EXPLANATION),
                     'explanation': st.column_config.TextColumn('Varför detta resultat?', width='large'),
                 })
    with st.expander('Visa tekniska matchningsdetaljer', expanded=False):
        st.caption('Källposition (från 0) kopplar varje kandidat till sin källrad. '
                   'Leverantörsnyckeln kopplar kandidaten till registeravtalen. '
                   'Samtliga kandidater i den aktuella vyn visas i samma ordning som ovan. '
                   'supplier_match_status i kandidatjämförelsen avser källradens beslut; '
                   'vald identitet anges av matched_organization_number i källradens resultat.')
        st.markdown('**Matchningsresultat per källrad – backendens ursprungliga uppgifter**')
        st.dataframe(matches, hide_index=True, width='stretch', column_config={
            **REGISTRY_ORGANIZATION_COLUMNS, 'candidate_count': 'Antal möjliga leverantörer',
        })
        if not candidates.empty:
            st.markdown('**Registerkandidater – backendens ursprungliga uppgifter**')
            st.dataframe(supplier_candidate_comparisons(matches, candidates), hide_index=True,
                         width='stretch', column_config=REGISTRY_ORGANIZATION_COLUMNS)
