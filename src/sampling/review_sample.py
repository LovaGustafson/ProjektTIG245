"""Download samples reuse confirmed verification/supplier rules, capped at 20."""
from src.sampling.manual_sample import plan_manual_sample, plan_random_sample


REVIEW_SAMPLE_INTERVAL = 20
REVIEW_SAMPLE_SEED = 42
REVIEW_SAMPLE_LIMIT = 20


def plan_review_sample(verifications, method, *, supplier_analysis=None, classification_rules=(),
                       seed=REVIEW_SAMPLE_SEED):
    """Select complete groups with existing identity, uniqueness and quota rules.

    Systematic retains nominal every-20th positions and forward replacement,
    capped at 20. Randomized retains the established target of 20. Both consume
    the completed analysis and saved classification rules, never live settings.
    """
    if method == 'systematic':
        return plan_manual_sample(verifications, interval=REVIEW_SAMPLE_INTERVAL,
                                  max_size=REVIEW_SAMPLE_LIMIT, supplier_analysis=supplier_analysis,
                                  classification_rules=classification_rules)
    if method == 'randomized':
        return plan_random_sample(verifications, seed=seed, supplier_analysis=supplier_analysis,
                                  classification_rules=classification_rules)
    raise ValueError('Unknown review sampling method')
