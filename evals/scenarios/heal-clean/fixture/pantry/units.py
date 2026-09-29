"""Mass and volume conversion tables."""

MASS_G = {"g": 1.0, "kg": 1000.0, "oz": 28.349523125, "lb": 453.59237}
VOLUME_ML = {"ml": 1.0, "l": 1000.0, "tsp": 4.92892159375, "tbsp": 14.78676478125, "cup": 236.5882365}
ALIASES = {
    "cups": "cup", "gram": "g", "grams": "g", "teaspoon": "tsp", "teaspoons": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "litre": "l", "litres": "l",
    "ounce": "oz", "ounces": "oz", "pound": "lb", "pounds": "lb", "lbs": "lb",
}


def canonical(unit):
    u = unit.lower()
    return ALIASES.get(u, u)


def is_unit(unit):
    u = canonical(unit)
    return u in MASS_G or u in VOLUME_ML


def convert(amount, src, dst):
    src, dst = canonical(src), canonical(dst)
    for table in (MASS_G, VOLUME_ML):
        if src in table and dst in table:
            return amount * table[src] / table[dst]
    raise ValueError(f"cannot convert {src} to {dst}")


def to_metric(amount, unit):
    unit = canonical(unit)
    if unit in MASS_G:
        return amount * MASS_G[unit], "g"
    if unit in VOLUME_ML:
        return amount * VOLUME_ML[unit], "ml"
    return amount, unit
