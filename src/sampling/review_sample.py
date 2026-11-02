"""Download-only row samples; independent of verification-level sampling."""
from random import Random


REVIEW_SAMPLE_INTERVAL = 20
REVIEW_SAMPLE_SEED = 42


def review_sample_positions(population_size: int, method: str, *, seed=REVIEW_SAMPLE_SEED) -> list[int]:
    """Return zero-based offsets in retained source order, without replacement.

    Both methods select floor(population_size / 20) source occurrences. Random
    selection uses a local generator and is returned in population order. Callers
    must supply the full retained review population, before temporary UI filters.
    Duplicate/missing business identifiers do not merge source occurrences.
    """
    if population_size < 0:
        raise ValueError('Population size must be non-negative')
    if method == 'systematic':
        return list(range(REVIEW_SAMPLE_INTERVAL - 1, population_size, REVIEW_SAMPLE_INTERVAL))
    if method == 'randomized':
        return sorted(Random(seed).sample(range(population_size), population_size // REVIEW_SAMPLE_INTERVAL))
    raise ValueError('Unknown review row sampling method')
