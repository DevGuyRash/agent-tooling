//! The club's Portsmouth Numbers, which results scores with and startline sets pursuit starts by.

use crate::Boat;

/// The Portsmouth Numbers the club races to: the RYA list for 2026, plus the club's own number for the
/// Feva XL, which the RYA doesn't list. Class names exactly as race files write them. Updated every March,
/// when the RYA publishes the new list.
const PORTSMOUTH_NUMBERS: &[(&str, u32)] = &[
    ("Comet", 1210),
    ("Enterprise", 1116),
    ("Finn", 1049),
    ("GP14", 1130),
    ("ILCA 4", 1207),
    ("ILCA 6", 1147),
    ("ILCA 7", 1100),
    ("Mirror", 1386),
    ("Optimist", 1642),
    ("RS Aero 7", 1063),
    ("RS Feva XL", 1240),
    ("RS200", 1047),
    ("RS400", 942),
    ("Solo", 1142),
    ("Topper", 1364),
    ("Wayfarer", 1102),
];

/// The Portsmouth Number of a boat's class, or the message both tools give when the class has none.
pub fn portsmouth_number(boat: &Boat) -> Result<u32, String> {
    PORTSMOUTH_NUMBERS
        .iter()
        .find(|(class, _)| *class == boat.class)
        .map(|&(_, pn)| pn)
        .ok_or_else(|| format!("line {}: no Portsmouth Number for class {:?}", boat.line, boat.class))
}
