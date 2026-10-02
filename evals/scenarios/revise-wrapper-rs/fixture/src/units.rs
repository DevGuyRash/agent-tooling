//! The units file: each fridge or freezer and its safe range, `UNIT<TAB>LOW<TAB>HIGH` (docs/format.md).

use crate::log::parse_tenths;
use crate::Failure;

pub struct Units {
    /// (unit, lowest safe tenths, highest safe tenths), in the file's order.
    ranges: Vec<(String, i32, i32)>,
}

impl Units {
    /// A unit's safe range in tenths, both ends included; None for a unit the file does not list.
    pub fn range(&self, unit: &str) -> Option<(i32, i32)> {
        self.ranges.iter().find(|(name, _, _)| name == unit).map(|&(_, low, high)| (low, high))
    }
}

pub fn read_file(path: &str) -> Result<Units, Failure> {
    let text = std::fs::read_to_string(path).map_err(|e| Failure::Data(format!("{path}: cannot read: {e}")))?;
    parse(&text).map_err(|(line, msg)| Failure::Data(format!("{path}:{line}: {msg}")))
}

pub fn parse(text: &str) -> Result<Units, (usize, String)> {
    let mut ranges: Vec<(String, i32, i32)> = Vec::new();
    for (i, line) in text.lines().enumerate() {
        if line.trim().is_empty() || line.starts_with('#') {
            continue;
        }
        let fields: Vec<&str> = line.split('\t').collect();
        let [unit, low, high] = fields[..] else {
            return Err((i + 1, "expected unit, low, and high separated by tabs".into()));
        };
        if unit.trim().is_empty() || unit.trim() != unit {
            return Err((i + 1, format!("bad unit name {unit:?}")));
        }
        let (Some(low), Some(high)) = (parse_tenths(low), parse_tenths(high)) else {
            return Err((i + 1, "limits are degrees with one decimal, like -18.0".into()));
        };
        if low > high {
            return Err((i + 1, format!("{unit}: low limit above high limit")));
        }
        if ranges.iter().any(|(name, _, _)| name == unit) {
            return Err((i + 1, format!("{unit} is listed twice")));
        }
        ranges.push((unit.to_string(), low, high));
    }
    Ok(Units { ranges })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_ranges() {
        let units = parse("# unit\tlow\thigh\ncongélateur-1\t-25.0\t-18.0\nfrigo-lait\t0.0\t4.0\n").ok().unwrap();
        assert_eq!(units.range("congélateur-1"), Some((-250, -180)));
        assert_eq!(units.range("frigo-lait"), Some((0, 40)));
        assert_eq!(units.range("frigo-cave"), None);
    }

    #[test]
    fn rejects_inverted_and_repeated_units() {
        assert_eq!(parse("frigo-lait\t4.0\t0.0\n").err().unwrap().0, 1);
        assert_eq!(parse("frigo-lait\t0.0\t4.0\nfrigo-lait\t0.0\t5.0\n").err().unwrap().0, 2);
    }
}
