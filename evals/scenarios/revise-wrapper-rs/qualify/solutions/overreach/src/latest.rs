//! `froid latest`: each unit's most recent reading and whether it is inside the unit's range, by unit name.

use std::collections::BTreeMap;

use crate::log::{degrees, Reading};
use crate::table::{render, Align};
use crate::units::Units;

pub fn report(units: &Units, readings: &[Reading]) -> String {
    let mut latest: BTreeMap<&str, &Reading> = BTreeMap::new();
    for r in readings {
        let newer = latest.get(r.unit.as_str()).map_or(true, |l| (&r.date, &r.clock) >= (&l.date, &l.clock));
        if newer {
            latest.insert(&r.unit, r);
        }
    }
    if latest.is_empty() {
        return "no readings\n".into();
    }
    let rows: Vec<Vec<String>> = latest
        .values()
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
