"""Deterministic organization-number fixtures; no claim of registered identity."""


def org(n: int) -> str:
    """Build a ten-digit Luhn-valid fixture from a six-digit test sequence."""
    if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= 999999:
        raise ValueError('Synthetic organization sequence must be an integer from 0 to 999999.')
    prefix = f'559{n:06d}'
    total = sum(sum(divmod(int(digit) * (2 if index % 2 == 0 else 1), 10))
                for index, digit in enumerate(prefix))
    return prefix + str(-total % 10)
