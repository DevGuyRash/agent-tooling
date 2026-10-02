//! The club's Portsmouth Numbers (data/portsmouth-numbers.toml, compiled in), which results scores with and
//! startline sets pursuit starts by.

use crate::Boat;

const LIST: &str = include_str!("../data/portsmouth-numbers.toml");

/// The Portsmouth Number of a boat's class, or the message both tools give when the class has none.
pub fn portsmouth_number(boat: &Boat) -> Result<u32, String> {
    LIST.lines()
        .map(str::trim)
        .filter(|l| !l.is_empty() && !l.starts_with('#') && !l.starts_with('['))
        .filter_map(|l| l.split_once('='))
        .map(|(k, v)| (k.trim().trim_matches('"'), v.trim()))
        .find(|(class, _)| *class == boat.class)
        .and_then(|(_, pn)| pn.parse().ok())
        .ok_or_else(|| format!("line {}: no Portsmouth Number for class {:?}", boat.line, boat.class))
}
