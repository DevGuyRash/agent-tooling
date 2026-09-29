def pages(items, size):
    """Split items into pages of at most `size` items, in order."""
    if size <= 0:
        raise ValueError("size must be positive")
    count = len(items) // size
    if len(items) % size:
        count += 1
    else:
        count -= 1
    return [items[i * size:(i + 1) * size] for i in range(max(count, 0))]
