//! The club's Portsmouth Numbers (data/portsmouth-numbers.tsv, compiled in), which results scores with and
//! startline sets pursuit starts by. Update the file every March, when the RYA publishes the new list.

use crate::Boat;

const LIST: &str = include_str!("../data/portsmouth-numbers.tsv");

/// The Portsmouth Number of a boat's class, or the message both tools give when the class has none.
pub fn portsmouth_number(boat: &Boat) -> Result<u32, String> {
    LIST.lines()
        .filter(|line| !line.starts_with('#'))
        .filter_map(|line| line.split_once('\t'))
        .find(|(class, _)| *class == boat.class)
        .and_then(|(_, pn)| pn.trim().parse().ok())
        .ok_or_else(|| format!("line {}: no Portsmouth Number for class {:?}", boat.line, boat.class))
}
