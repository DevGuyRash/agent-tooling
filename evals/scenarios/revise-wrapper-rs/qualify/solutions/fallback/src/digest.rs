//! `froid digest`: one line per unit and day (docs/digest.md). Where python3 is installed froid runs
//! tools/digest.py as before; on hosts without it (the kiosk) it makes the same digest itself.

use std::cmp::Ordering;
use std::collections::BTreeMap;
use std::io::ErrorKind;
use std::process::{Command, ExitCode};

use crate::Failure;

use crate::log::{degrees, Reading};
use crate::table::{render, Align};
use crate::units::Units;

const HEADER: [&str; 9] = ["unit", "day", "n", "min", "max", "mean", "median", "out", "worst"];
const ALIGN: [Align; 9] = [
    Align::Left,
    Align::Left,
    Align::Right,
    Align::Right,
    Align::Right,
    Align::Right,
    Align::Right,
    Align::Right,
    Align::Left,
];

/// The script, in the checkout froid is built from.
const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/tools/digest.py");

pub fn run(units_path: &str, units: &Units, readings: &[Reading], day: Option<&str>, logs: &[String]) -> Result<ExitCode, Failure> {
    let mut cmd = Command::new("python3");
    cmd.arg(SCRIPT).arg("--units").arg(units_path);
    if let Some(day) = day {
        cmd.arg("--day").arg(day);
    }
    cmd.arg("--").args(logs);
    match cmd.status() {
        Ok(status) if status.success() => Ok(ExitCode::SUCCESS),
        Ok(status) => Err(Failure::Data(format!("digest: tools/digest.py failed ({status})"))),
        Err(e) if e.kind() == ErrorKind::NotFound => {
            print!("{}", report(units, readings, day));
            Ok(ExitCode::SUCCESS)
        }
        Err(e) => Err(Failure::Data(format!("digest: cannot run python3: {e}"))),
    }
}

/// The digest of `readings` (in the exports' order), only `day`'s when one is given.
fn report(units: &Units, readings: &[Reading], day: Option<&str>) -> String {
    // Units in the order they first appear, each unit's days in date order, readings in the exports' order.
    let mut by_unit: Vec<(&str, BTreeMap<&str, Vec<&Reading>>)> = Vec::new();
    for r in readings.iter().filter(|r| day.map_or(true, |d| r.date == d)) {
        let i = match by_unit.iter().position(|(unit, _)| *unit == r.unit) {
            Some(i) => i,
            None => {
                by_unit.push((&r.unit, BTreeMap::new()));
                by_unit.len() - 1
            }
        };
        by_unit[i].1.entry(&r.date).or_default().push(r);
    }
    let mut rows = Vec::new();
    let mut out_total = 0;
    for (unit, days) in &by_unit {
        for (date, day_readings) in days {
            let (row, out) = row(unit, date, day_readings, units.range(unit));
            out_total += out;
            rows.push(row);
        }
    }
    if rows.is_empty() {
        return match day {
            Some(day) => format!("no readings on {day}\n"),
            None => "no readings\n".to_string(),
        };
    }
    format!(
        "{}\n{}, {} out of range\n",
        render(&HEADER, &ALIGN, &rows),
        plural(rows.len(), "unit-day"),
        plural(out_total, "reading")
    )
}

fn row(unit: &str, date: &str, readings: &[&Reading], range: Option<(i32, i32)>) -> (Vec<String>, usize) {
    let mut temps: Vec<i32> = readings.iter().map(|r| r.tenths).collect();
    let n = temps.len() as i64;
    let sum: i64 = temps.iter().map(|&t| i64::from(t)).sum();
    temps.sort_unstable();
    let mid = temps.len() / 2;
    let median = if temps.len() % 2 == 1 {
        i64::from(temps[mid])
    } else {
        halves_to_even(i64::from(temps[mid - 1]) + i64::from(temps[mid]), 2)
    };
    let mut row = vec![
        unit.to_string(),
        date.to_string(),
        temps.len().to_string(),
        degrees(temps[0]),
        degrees(temps[temps.len() - 1]),
        degrees(halves_to_even(sum, n) as i32),
        degrees(median as i32),
    ];
    let Some((low, high)) = range else {
        row.extend(["-".to_string(), "-".to_string()]);
        return (row, 0);
    };
    let mut out = 0;
    let mut worst: Option<(i32, &Reading)> = None;
    for r in readings {
        let by = (low - r.tenths).max(r.tenths - high).max(0);
        if by == 0 {
            continue;
        }
        out += 1;
        // The first of equally bad readings stays.
        if worst.map_or(true, |(w, _)| by > w) {
            worst = Some((by, r));
        }
    }
    row.push(out.to_string());
    row.push(match worst {
        Some((_, r)) => format!("{} at {}", degrees(r.tenths), r.clock),
        None => "-".to_string(),
    });
    (row, out)
}

/// `p / q` (q > 0) to the nearest whole number; exactly halfway goes to the even one.
fn halves_to_even(p: i64, q: i64) -> i64 {
    let (floor, rem) = (p.div_euclid(q), p.rem_euclid(q));
    match (2 * rem).cmp(&q) {
        Ordering::Less => floor,
        Ordering::Greater => floor + 1,
        Ordering::Equal if floor % 2 == 0 => floor,
        Ordering::Equal => floor + 1,
    }
}

fn plural(n: usize, word: &str) -> String {
    format!("{n} {word}{}", if n == 1 { "" } else { "s" })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn halves_go_to_even() {
        assert_eq!(halves_to_even(-369, 2), -184);
        assert_eq!(halves_to_even(-363, 2), -182);
        assert_eq!(halves_to_even(45, 2), 22);
        assert_eq!(halves_to_even(47, 2), 24);
        assert_eq!(halves_to_even(-1, 4), 0);
        assert_eq!(halves_to_even(-3, 4), -1);
    }
}
