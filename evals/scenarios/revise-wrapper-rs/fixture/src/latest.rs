//! `froid latest`: each unit's most recent reading and whether it is inside the unit's range.

use crate::log::{degrees, Reading};
use crate::table::{render, Align};
use crate::units::Units;

pub fn report(units: &Units, readings: &[Reading]) -> String {
    // Units in the order they first appear; a later line wins when two readings share a time.
    let mut latest: Vec<&Reading> = Vec::new();
    for r in readings {
        match latest.iter_mut().find(|l| l.unit == r.unit) {
            Some(l) if (r.date.as_str(), r.clock.as_str()) >= (l.date.as_str(), l.clock.as_str()) => *l = r,
            Some(_) => {}
            None => latest.push(r),
        }
    }
    if latest.is_empty() {
        return "no readings\n".into();
    }
    let rows: Vec<Vec<String>> = latest
        .iter()
        .map(|r| {
            let status = match units.range(&r.unit) {
                None => "no range",
                Some((low, _)) if r.tenths < low => "too cold",
                Some((_, high)) if r.tenths > high => "too warm",
                Some(_) => "ok",
            };
            vec![r.unit.clone(), format!("{} {}", r.date, r.clock), degrees(r.tenths), status.to_string()]
        })
        .collect();
    render(&["unit", "time", "temp", "status"], &[Align::Left, Align::Left, Align::Right, Align::Left], &rows)
}
