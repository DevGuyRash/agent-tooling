import random


def sample_mean(values, k=3):
    """Mean of k values drawn without replacement."""
    picked = random.sample(values, k)
    return sum(picked) / k
