import sys
import timeit

impl = __import__(sys.argv[1])
names = ["  Ada   Lovelace ", "JOSÉ  Núñez", "Grace Hopper"] * 1000
print(sys.argv[1], round(min(timeit.repeat(lambda: [impl.normalize_name(n) for n in names], number=5, repeat=3)), 4), "s")
