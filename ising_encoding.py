"""Exact binary-to-spin substitution x=(1-Z)/2, with uniform energy scaling."""


def coefficients(n, terms, offset):
    scale = max(1, max((abs(v) for i, j, v in terms), default=0))
    h = [0.0] * n
    pairs = []
    constant = offset
    for i, j, v in terms:
        if i == j:
            h[i] -= v / 2 / scale
            constant += v / 2
        else:
            h[i] -= v / 4 / scale
            h[j] -= v / 4 / scale
            pairs.append((i, j, v / 4 / scale))
            constant += v / 4
    return scale, constant / scale, h, pairs
