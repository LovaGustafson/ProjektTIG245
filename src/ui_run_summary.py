"""Visual presentation of existing run evidence; no selection or business rules."""
import pandas as pd
import streamlit as st

from src.models.result import CheckStatus
from src.models.supplier import SupplierMatchStatus
from src.run_summary import SAMPLE_ORDER, SAMPLE_POPULATION, SAMPLE_METHOD, SAMPLE_IDENTITY
from src.supplier_matching.view_scope import visible_supplier_analysis
from src.ui_supplier_panel import show_supplier_scope
from src.ui_support import display_dataframe
from src.ui_overview_details import (
    source_rows, reason_counts, supplier_details,
    contract_details, exclusion_details, verification_details,
)


SUPPLIER_LABELS = {
    'STRONG_MATCH': 'Stark leverantörsträff',
    'AMBIGUOUS_MATCH': 'Osäker träff',
    'NO_MATCH': 'Ingen träff i registret',
    'SUPPLIER_NOT_IDENTIFIED': 'Leverantör ej identifierad',
}
CONTRACT_LABELS = {
    'PASS': 'Inom avtalsperiod', 'FLAGGED': 'Utanför avtalsperiod',
    'ERROR': 'Tekniskt fel', 'NOT_CHECKED': 'Ej verifierbar',
}
EXCLUSION_LABELS = {
    'account': 'Konto', 'verification_type': 'Verifikationstyp',
    'internal_supplier': 'Intern leverantör', 'structural_row': 'Strukturell rad',
}
STATUS_COLORS = ['#126b78', '#b66a12', '#b33d4b', '#788494']
CONTRACT_EXPLANATIONS = {
    'PASS': 'Verifikationsdatum ligger inom den jämförda registerpostens avtalsperiod. '
            'Vilket avtal köpet omfattas av har inte kontrollerats.',
    'FLAGGED': 'Datumjämförelsen visar att verifikationsdatum ligger före eller efter '
               'den jämförda avtalsperioden. Backend-resultatet anger vilket.',
    'ERROR': 'Avtalsjämförelsen kunde inte slutföras tillförlitligt. Se registrerad orsak.',
    'NOT_CHECKED': 'Underlaget eller de bekräftade datumreglerna räcker inte för att bedöma '
                   'denna avtalsperiod. Det betyder inte att avtal saknas eller är ogiltigt. '
                   'Det är separat från att datumet faktiskt ligger utanför perioden.',
}
SUPPLIER_EXPLANATIONS = {
    'STRONG_MATCH': 'Matchningsmotorn har identifierat en stark leverantörsträff i det använda registret. '
                    'Antalet avser kvarvarande källrader, inte unika leverantörer eller verifikationer. '
                    'Träffen fastställer inte avtalsefterlevnad.',
    'AMBIGUOUS_MATCH': 'Leverantörsidentiteten är osäker och behöver granskas manuellt. '
                       'Ingen leverantör har valts automatiskt. Matchningsmotorns orsaker och '
                       'eventuella kandidater visas nedan.',
    'NO_MATCH': 'Matchningsmotorn hittade ingen träff i det använda registret. '
                'Det fastställer inte att leverantören saknar avtal.',
    'SUPPLIER_NOT_IDENTIFIED': 'Leverantören kunde inte identifieras från Huvudtext enligt '
                               'de befintliga extraktionsreglerna. Se motorns faktiska orsak nedan.',
}
DETAIL_COLUMNS = {
    'source_row_position': 'Källposition (från 0)',
    'source_row_positions': 'Källpositioner (från 0)',
    'source_excel_row': 'Rad i Excel', 'source_sheet': 'Kalkylblad',
    'source_link': 'Källkoppling', 'exclusion_reason': 'Exkluderingsorsak',
    'population_position': 'Position i urvalspopulationen', 'row_count': 'Antal källrader',
    'verification_id': 'Verifikation', 'verification_line_id': 'Verifikationsrad',
    'supplier': 'Leverantör',
    'row_position': 'row_position (inom verifikationen, från 0)',
    'check_type': 'Kontroll (check_type)', 'field': 'Fält (field)',
    'reason': 'Orsak (reason)', 'status': 'Status (status)',
    'supplier_match_reason': 'Matchningsorsak (supplier_match_reason)',
    'supplier_match_status': 'Matchningsstatus (supplier_match_status)',
    'supplier_text_raw': 'Leverantör från Huvudtext',
    'matched_supplier_name': 'Identifierad leverantör', 'supplier_name': 'Leverantör/kandidat',
    'contract_period_status': 'Status (contract_period_status)',
    'contract_period_reason': 'Orsak (contract_period_reason)',
    'contract_period_result': 'Resultat (contract_period_result)',
    'contract_id': 'Avtals-ID', 'contract_name': 'Avtalsnamn',
    'verification_date': 'Verifikationsdatum',
    'start_date': 'Startdatum (original)', 'end_date': 'Slutdatum (original)',
    'final_end_date': 'Sista slutdatum (original)',
    'supplier_key': 'Leverantörsnyckel', 'identity_basis': 'Grund för leverantörsnyckel',
    'identity_reason': 'Identitetsbedömning', 'identity_usable': 'En gemensam användbar leverantörsnyckel',
    'decision': 'Urvalsbeslut (decision)', 'selection_reason': 'Orsak till urvalsbeslut',
    'nominal_position': 'Ordinarie urvalsposition',
    'duplicate_of_population_position': 'Leverantör redan vald på position',
}


def show_evidence(data, title):
    st.markdown(f'**{title}**')
    if data.empty:
        st.caption('Inga poster i denna kategori.')
    else:
        st.dataframe(display_dataframe(data), hide_index=True, width='stretch',
                     column_config=DETAIL_COLUMNS)


def show_source_rows(rows):
    st.caption('Källposition identifierar raden i den inlästa tabellen (från 0). '
               'Excel-rad och kalkylblad visas när de finns. Huvudtext visas med '
               'befintlig visningsrensning av numrerade Slutk-markörer; källvärdena bevaras internt.')
    show_evidence(rows, 'Underliggande källrader')


def show_supplier_drilldowns(result, counts):
    for row in counts.itertuples(index=False):
        with st.expander(f'{row.Kategori} · {row.Antal} rader', expanded=False):
            st.write(SUPPLIER_EXPLANATIONS[row.Status])
            matches, candidates, contracts, rows = supplier_details(result, row.Status)
            show_evidence(reason_counts(matches, ['supplier_match_reason']), 'Registrerade orsaker · antal rader')
            show_evidence(matches, 'Matchningsresultat per källrad')
            show_source_rows(rows)
            st.caption('Kandidater och avtal hör till samma källposition som matchningsresultatet. '
                       'Flera kandidater eller avtal kan finnas per rad. Score är namnlikhet, inte sannolikhet.')
            show_evidence(candidates, 'Befintliga leverantörskandidater och matchningsorsaker')
            with st.expander('Befintlig avtalsinformation', expanded=False):
                show_evidence(contracts, 'Möjliga registeravtal · inget avtal har valts för köpet')


def show_contract_drilldowns(result, counts):
    analysis = result.supplier_analysis
    if analysis is None or not analysis.registry.available:
        st.caption('Avtalsevidens saknas när leverantörsmatchningen är otillgänglig.')
        return
    for row in counts.itertuples(index=False):
        with st.expander(f'{row.Kategori} · {row.Antal} avtalsjämförelser', expanded=False):
            st.write(CONTRACT_EXPLANATIONS[row.Status])
            contracts, rows = contract_details(result, row.Status)
            show_evidence(reason_counts(contracts, ['contract_period_reason']),
                          'Registrerade orsaker · antal avtalsjämförelser')
            show_evidence(contracts, 'Faktiska avtalsjämförelser med leverantör, datum och status')
            show_source_rows(rows)
    st.caption('För rader utan någon leverantörskandidat finns ingen avtalsjämförelse i backend. '
               'De räknas inte i denna fördelning; deras evidens finns under Leverantörsmatchning.')


def show_verification_drilldown(result, key, label, count, explanation):
    with st.expander(f'{label} · {count} verifikationer', expanded=False):
        st.write(explanation)
        groups, rows = verification_details(result, key)
        show_evidence(groups, 'Verifikationer och deras källpositioner')
        show_source_rows(rows)


def _counts_table(counts, labels):
    """Retain evidence keys alongside readable labels, including zero counts."""
    return pd.DataFrame([
        {'Kategori': labels.get(key, key), 'Antal': int(value), 'Status': str(key)}
        for key, value in counts.items()
    ], columns=['Kategori', 'Antal', 'Status'])


def dashboard_tables(result):
    """Build display copies from RunSummary/evidence and explicit supplier-view scope.

    Exclusions are recorded rule hits (potentially overlapping). Supplier counts
    are occurrences in the supplier view, contracts are full-run comparisons.
    An unavailable register supplies no supplier-status distribution.
    """
    s = result.summary
    if s is None:
        return {}
    exclusion_labels = {}
    for rule in s.exclusion_counts:
        kind, _, expression = rule.partition(': ')
        exclusion_labels[rule] = f'{EXCLUSION_LABELS.get(kind, kind)} – {expression}'
    analysis = visible_supplier_analysis(result.supplier_analysis, result.supplier_view)
    supplier_counts = {}
    if analysis is not None and analysis.registry.available:
        counts = analysis.rows['supplier_match_status'].value_counts()
        supplier_counts = {status.value: counts.get(status, 0) for status in SupplierMatchStatus}
    return {
        'population': _counts_table(
            {'included': s.included_rows, 'excluded': s.excluded_rows},
            {'included': 'Kvarvarande', 'excluded': 'Exkluderade'}),
        'exclusions': _counts_table(s.exclusion_counts, exclusion_labels),
        'suppliers': _counts_table(supplier_counts, SUPPLIER_LABELS),
        'contracts': _counts_table(
            {status.value: s.contract_status_counts.get(status, 0) for status in CheckStatus}, CONTRACT_LABELS),
        'sample': _counts_table(
            {'selected': s.sampled_verifications,
             'remaining': s.eligible_verifications - s.sampled_verifications},
            {'selected': 'Utvalda', 'remaining': 'Övriga i urvalspopulationen'}),
    }


def show_count_chart(data, *, unit, key, colors=None, empty_message):
    """Native Streamlit/Vega-Lite bars with exact values, labels and tooltips."""
    if data.empty or not data['Antal'].sum():
        st.info(empty_message)
        return
    spec = {
        'height': max(120, len(data) * 44),
        'padding': {'right': 35},
        'encoding': {
            'y': {'field': 'Kategori', 'type': 'nominal', 'sort': None,
                  'axis': {'title': None, 'labelLimit': 230}},
            'x': {'field': 'Antal', 'type': 'quantitative',
                  'scale': {'zero': True, 'nice': True},
                  'axis': {'title': unit, 'tickMinStep': 1, 'format': 'd'}},
            'tooltip': [{'field': 'Kategori', 'type': 'nominal'},
                        {'field': 'Antal', 'type': 'quantitative', 'title': unit, 'format': 'd'}],
        },
        'layer': [
            {'mark': {'type': 'bar', 'cornerRadiusEnd': 4, 'size': 23},
             'encoding': {'color': {'field': 'Status', 'type': 'nominal', 'legend': None,
                          'scale': {'domain': data['Status'].tolist(),
                                    'range': colors or ['#126b78'] * len(data)}}}},
            {'mark': {'type': 'text', 'align': 'left', 'dx': 7},
             'encoding': {'text': {'field': 'Antal', 'type': 'quantitative', 'format': 'd'}}},
        ],
    }
    st.vega_lite_chart(data, spec, width='stretch', key=key)


def show_run_summary(result):
    s = result.summary
    if s is None:
        return
    charts = dashboard_tables(result)
    st.subheader('Analysöversikt')
    st.caption('Hela analyskörningen. Tillfälliga vyfilter ändrar inte dessa antal eller exporterna.')
    st.caption('Öppna en kategori under diagrammen för förklaring, registrerade orsaker och underliggande poster.')
    with st.container(key='overview_kpis'):
        for column, label, value in zip(st.columns(5),
                ['Källpopulation · rader', 'Kvarvarande · rader', 'Exkluderade · rader',
                 'Flaggade · verifikationer', 'Manuellt urval · verifikationer'],
                [s.source_rows, s.included_rows, s.excluded_rows,
                 s.flagged_verifications, s.sampled_verifications]):
            column.metric(label, value)

    st.html('<ol class="audit-steps" aria-label="Analysens steg">'
            '<li><span>1</span>Källfil</li><li><span>2</span>Filtrering → kvarvarande</li>'
            '<li><span>3</span>Leverantörsmatchning</li><li><span>4</span>Avtalsperioder</li>'
            '<li><span>5</span>Granskning</li><li><span>6</span>Stickprov / export</li></ol>')
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown('#### Populationens flöde')
        st.caption(f'{s.source_rows} källrader = {s.included_rows} kvarvarande + {s.excluded_rows} exkluderade.')
        show_count_chart(charts['population'], unit='Källrader', key='chart_population',
                         colors=['#126b78', '#788494'], empty_message='Inga inlästa källrader.')
        st.caption('Avser den inlästa tabellen i första kalkylbladet. '
                   'Fullständighet gentemot Proceedo är inte verifierad.')
        for label, positions in [
            ('Källpopulation', result.original_data.index),
            ('Kvarvarande', result.filtering.cleaned_data.index),
            ('Exkluderade', result.filtering.excluded_data.index),
            ('Utan användbart verifikations-ID', result.ungrouped_data.index),
        ]:
            with st.expander(f'{label} · {len(positions)} rader', expanded=False):
                st.write('Befintliga källrader i denna del av körningen. Exkluderade rader '
                         'visar samtliga registrerade exkluderingsorsaker. Kvarvarande '
                         'rader är underlag för fortsatt granskning, inte automatiskt godkända.')
                show_source_rows(source_rows(result, positions))
    with right, st.container(border=True):
        st.markdown('#### Leverantörsmatchning')
        show_supplier_scope(result)
        analysis = visible_supplier_analysis(result.supplier_analysis, result.supplier_view)
        if analysis is None or not analysis.registry.available:
            st.info(f'Matchning ej tillgänglig för {s.supplier_unavailable_rows} kvarvarande rader. '
                    'Register saknas eller är oanvändbart.')
            with st.expander('Matchning ej tillgänglig – förklaring och rader', expanded=False):
                st.write('Ingen matchningsstatus har kunnat fastställas för dessa rader. '
                         'Otillgänglig matchning är inte samma sak som ingen träff i registret.')
                if analysis is not None:
                    for issue in analysis.registry.issues:
                        st.text(issue)
                show_source_rows(source_rows(result, result.filtering.cleaned_data.index))
        else:
            show_count_chart(charts['suppliers'], unit='Kvarvarande rader', key='chart_suppliers',
                             colors=['#126b78', '#b66a12', '#b33d4b', '#788494'],
                             empty_message='Inga kvarvarande rader att matcha.')
            show_supplier_drilldowns(result, charts['suppliers'])
        st.caption(f'Hela körningen: {s.uncertain_supplier_rows} rader utan säker leverantörsträff. '
                   'Leverantörsidentitet är separat från avtalsefterlevnad. Öppna kategorierna ovan för evidens.')

    with st.expander('Varför exkluderades rader?', expanded=False):
        st.caption('Faktiska regelträffar. En rad kan träffa flera regler; staplarna ska inte summeras '
                   'till antal unika exkluderade rader.')
        show_count_chart(charts['exclusions'], unit='Regelträffar (rader)', key='chart_exclusions',
                         empty_message='Inga exkluderingsorsaker i denna körning.')
        for row in charts['exclusions'].itertuples(index=False):
            with st.expander(f'{row.Kategori} · {row.Antal} regelträffar', expanded=False):
                show_source_rows(exclusion_details(result, row.Status))

    st.subheader('Avvikelser och avtalsperioder')
    st.caption(f'{s.flagged_verifications} flaggade verifikationer med {s.flagged_rows} tillhörande rader. '
               'Tekniska fel redovisas separat under Kontroller.')
    show_verification_drilldown(result, 'flagged', 'Flaggade', s.flagged_verifications,
                               'Verifikationer med minst ett FLAGGED-resultat. '
                               'Orsakerna visas under Flaggade verifikationer i fliken Granskning.')
    st.info('Attestkontroll ej genomförd – kräver attestregister eller motsvarande behörighetsunderlag '
            'som inte finns tillgängligt i prototypen.')
    with st.container(border=True):
        st.markdown('#### Avtalsperioder vid verifikationsdatum')
        show_count_chart(charts['contracts'], unit='Avtalsjämförelser', key='chart_contracts',
                         colors=STATUS_COLORS, empty_message='Inga avtalsjämförelser kunde göras i denna körning.')
        st.caption('Varje möjligt registeravtal jämförs separat med källradens datum. '
                   'Inom perioden betyder inte att köpet omfattas av avtalet.')
        show_contract_drilldowns(result, charts['contracts'])

    with st.container(border=True, key='sample_overview'):
        st.subheader('Manuellt stickprov')
        for column, label, value in zip(st.columns(4),
                ['Verifikationer i urvalspopulationen', 'Ordinarie urvalsintervall',
                 'Valda verifikationer', 'Rader i stickprovet'],
                [s.eligible_verifications, f'Var {s.sample_interval}:e', s.sampled_verifications, s.sampled_rows]):
            column.metric(label, value)
        show_count_chart(charts['sample'], unit='Verifikationer', key='chart_sample',
                         colors=['#126b78', '#b7c4d2'], empty_message='Urvalspopulationen är tom.')
        st.caption(SAMPLE_POPULATION + ' ' + SAMPLE_ORDER)
        sampling = result.sampling_result
        if sampling is not None:
            st.caption(f'Önskat antal: {sampling.target_size} verifikationer. '
                       'Högst en vald verifikation per leverantörsnyckel/normaliserat namn.')
            if sampling.shortfall_message:
                st.warning(sampling.shortfall_message)
            with st.expander('Urvalsmetod, leverantörsunikhet och urvalsbeslut', expanded=False):
                st.write(SAMPLE_METHOD)
                st.write(SAMPLE_IDENTITY)
                show_evidence(sampling.decisions, 'Alla verifikationer · urvalsbeslut och orsaker')
                show_evidence(sampling.identity_rows, 'Leverantörsidentitet och källposition per rad')
                unusable = sampling.identity_rows.loc[sampling.identity_rows['population_position'].isin(
                    sampling.decisions.loc[~sampling.decisions['identity_usable'].astype(bool), 'population_position'])]
                with st.expander('Utanför stickprovet – saknad eller flera leverantörsidentiteter', expanded=False):
                    show_source_rows(source_rows(result, unusable['source_row_position']))
        with st.expander('Vad betyder urvalspopulation och stark leverantörsträff?', expanded=False):
            st.write('Urvalspopulationen räknar verifikationer: kvarvarande rader med användbart '
                     'verifikations-ID grupperas på det normaliserade ID:t. Varje grupp räknas en gång, '
                     'även om den innehåller flera rader. Valideringsfel i andra fält tar inte i sig '
                     'bort gruppen ur populationen. Flaggning påverkar inte urvalet.')
            st.write('Stark leverantörsträff räknar kvarvarande källrader med backend-status STRONG_MATCH. '
                     'Matchningsmotorn har då en enda tillräckligt säker leverantörskandidat med '
                     'organisationsnummer. Det är varken ett antal unika leverantörer eller ett '
                     'godkännande av köpets avtalsefterlevnad.')
            st.write('Siffrorna kan därför skilja sig: en verifikation kan innehålla flera matchade rader, '
                     'vissa rader får andra matchningsstatusar och även rader utan användbart '
                     'verifikations-ID kan leverantörsmatchas när registret är tillgängligt.')
            st.write('Leverantörsdiagrammet och dess kategorier avser raderna i leverantörsvyn. '
                     'Bekräftade vyexkluderingar redovisas separat. Körningens totaler nedan '
                     'och matchningsunderlaget i exporten omfattar även dessa rader.')
            st.text(f'Denna körning: {s.eligible_verifications} verifikationer i urvalspopulationen, '
                    f'{s.strong_supplier_rows} rader med stark leverantörsträff och '
                    f'{s.ungrouped_rows} kvarvarande rader utan användbart verifikations-ID.')
            if s.supplier_unavailable_rows:
                st.caption(f'Matchningen är otillgänglig för {s.supplier_unavailable_rows} rader; '
                           'dessa har ingen fastställd matchningsstatus.')
        show_verification_drilldown(result, 'all', 'Hela urvalspopulationen', s.eligible_verifications,
                                   SAMPLE_POPULATION + ' ' + SAMPLE_ORDER)
        for row in charts['sample'].itertuples(index=False):
            show_verification_drilldown(result, row.Status, row.Kategori, row.Antal,
                                       f'Stickprovet utgår från var {s.sample_interval}:e '
                                       'verifikation, med ersättning framåt för att hålla leverantörerna unika. '
                                       'Flaggning påverkar inte urvalet. '
                                       'Övriga grupper tillhör populationen men valdes inte till stickprovet.')
        st.caption('Granskningsstatus registreras inte i verktyget. Antal färdiggranskade kan därför inte visas. '
                   'Se urvalet under Manuell kontroll och hämta underlaget under Export.')
        if s.ungrouped_rows:
            st.warning(f'{s.ungrouped_rows} kvarvarande rader saknar användbart verifikations-ID. '
                       'De finns i granskningsunderlaget men ingår inte i det verifikationsbaserade stickprovet.')
