"""Run evidence shared by the pipeline, dashboard and exports."""
from collections import Counter
from dataclasses import dataclass

from src.models.supplier import SupplierMatchStatus

SAMPLE_ORDER = 'Första förekomst i källdata efter basfiltrering och gruppering; ingen omsortering.'
SAMPLE_POPULATION = ('Alla kvarvarande verifikationer med användbart verifikations-ID, '
                     'efter analys och oberoende av flaggning. Hela kvarvarande grupper väljs.')


@dataclass(frozen=True)
class RunSummary:
    source_rows: int
    included_rows: int
    excluded_rows: int
    ungrouped_rows: int
    eligible_verifications: int
    sample_interval: int
    sampled_verifications: int
    sampled_rows: int
    flagged_verifications: int
    flagged_rows: int
    supplier_analyzed_rows: int
    strong_supplier_rows: int
    uncertain_supplier_rows: int
    supplier_unavailable_rows: int
    exclusion_counts: dict[str, int]
    check_status_counts: dict[str, int]
    contract_status_counts: dict[str, int]

    def counts(self):
        counts = {
            'Inlästa källrader': self.source_rows,
            'Inkluderade rader': self.included_rows,
            'Exkluderade rader': self.excluded_rows,
            'Kvarvarande rader utan användbart verifikations-ID': self.ungrouped_rows,
            'Verifikationer i urvalspopulationen': self.eligible_verifications,
            'Stickprovsintervall': self.sample_interval,
            'Verifikationer för manuell granskning': self.sampled_verifications,
            'Rader i manuellt stickprov': self.sampled_rows,
            'Flaggade verifikationer': self.flagged_verifications,
            'Rader i flaggade verifikationer': self.flagged_rows,
            'Leverantörsmatchade rader': self.supplier_analyzed_rows,
            'Rader med säker leverantörsträff': self.strong_supplier_rows,
            'Rader utan säker leverantörsträff': self.uncertain_supplier_rows,
            'Rader där leverantörsmatchning inte kunde genomföras': self.supplier_unavailable_rows,
        }
        for status in ('PASS', 'FLAGGED', 'ERROR', 'NOT_CHECKED'):
            counts[f'Detektionskontroller: {status}'] = self.check_status_counts.get(status, 0)
            counts[f'Avtalsperioder (avtalsjämförelser): {status}'] = self.contract_status_counts.get(status, 0)
        return counts


def summarize_run(original, filtering, ungrouped, verifications, detections, sample,
                  analysis, interval):
    available = analysis is not None and analysis.registry.available
    strong = int((analysis.rows['supplier_match_status'] == SupplierMatchStatus.STRONG_MATCH).sum()) if available else 0
    flagged = [v for v, d in zip(verifications, detections) if d.flag_reasons]
    exclusions = {f'{rule}: {value}': len(positions)
                  for rule, values in filtering.rule_details.items()
                  for value, positions in values.items() if positions}
    contract_counts = (dict(Counter(analysis.contracts['contract_period_status']))
                       if available and 'contract_period_status' in analysis.contracts else {})
    return RunSummary(len(original), len(filtering.cleaned_data), len(filtering.excluded_data),
                      len(ungrouped), len(verifications), interval, len(sample),
                      sum(len(v.rows) for v in sample), len(flagged), sum(len(v.rows) for v in flagged),
                      len(analysis.rows) if available else 0, strong,
                      len(filtering.cleaned_data) - strong,
                      0 if available else len(filtering.cleaned_data), exclusions,
                      dict(Counter(c.status.value for d in detections for c in d.checks)), contract_counts)
