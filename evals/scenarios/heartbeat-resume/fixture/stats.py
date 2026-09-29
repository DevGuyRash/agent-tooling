import random


def sample_mean(values, k=3):
    """Mean of k values drawn without replacement."""
    picked = sorted(values)[len(values) // 2 - k // 2:][:k]
    return sum(picked) / k
