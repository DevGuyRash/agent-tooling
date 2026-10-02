//! `froid digest`: one line per unit and day, as docs/digest.md describes and tools/digest.py printed it.

mod stats;

use std::collections::HashMap;
use std::io::{self, Write};

use crate::log::{degrees, Reading};
use crate::units::Units;

struct Line {
    cells: [String; 8],
    worst: String,
    out: Option<usize>,
}

/// Writes the digest of `readings` to standard output.
pub fn print(units: &Units, readings: &[Reading], day: Option<&str>) -> io::Result<()> {
    let text = render(units, readings, day);
    let mut stdout = io::stdout().lock();
    stdout.write_all(text.as_bytes())?;
    stdout.flush()
}

fn render(units: &Units, readings: &[Reading], day: Option<&str>) -> String {
    // unit -> its position in first-seen order; (unit position, date) -> readings in the exports' order
    let mut seen: HashMap<&str, usize> = HashMap::new();
    let mut groups: HashMap<(usize, &str), Vec<&Reading>> = HashMap::new();
    let mut names: Vec<&str> = Vec::new();
    for r in readings {
        if day.is_some_and(|d| d != r.date) {
            continue;
        }
        let next = names.len();
        let pos = *seen.entry(r.unit.as_str()).or_insert(next);
        if pos == next {
            names.push(&r.unit);
        }
        groups.entry((pos, r.date.as_str())).or_default().push(r);
    }
    let mut keys: Vec<(usize, &str)> = groups.keys().copied().collect();
    keys.sort();
    let lines: Vec<Line> = keys.iter().map(|k| line(names[k.0], k.1, &groups[k], units)).collect();
    if lines.is_empty() {
        return day.map_or_else(|| "no readings\n".to_string(), |d| format!("no readings on {d}\n"));
    }
    let header = ["unit", "day", "n", "min", "max", "mean", "median", "out"];
    let mut width = header.map(|h| h.chars().count());
    for l in &lines {
        for (w, c) in width.iter_mut().zip(&l.cells) {
            *w = (*w).max(c.chars().count());
        }
    }
    let mut text = String::new();
    let mut emit = |cells: [&str; 8], last: &str| {
        for (i, (c, w)) in cells.iter().zip(width).enumerate() {
            let pad = " ".repeat(w - c.chars().count());
            if i < 2 {
                text.push_str(c);
                text.push_str(&pad);
            } else {
                text.push_str(&pad);
                text.push_str(c);
            }
            text.push_str("  ");
        }
        text.push_str(last);
        text.push('\n');
    };
    emit(header, "worst");
    for l in &lines {
        emit(l.cells.each_ref().map(String::as_str), &l.worst);
    }
    let out: usize = lines.iter().filter_map(|l| l.out).sum();
    let s = |n: usize| if n == 1 { "" } else { "s" };
    text.push_str(&format!("\n{} unit-day{}, {} reading{} out of range\n", lines.len(), s(lines.len()), out, s(out)));
    text
}

fn line(unit: &str, date: &str, readings: &[&Reading], units: &Units) -> Line {
    let temps: Vec<i32> = readings.iter().map(|r| r.tenths).collect();
    let (out, worst) = match units.range(unit) {
        Some((low, high)) => {
            let off = |t: i32| (low - t).max(t - high).max(0);
            let bad: Vec<&&Reading> = readings.iter().filter(|r| off(r.tenths) > 0).collect();
            let worst = bad.iter().fold(None::<&&Reading>, |w, r| match w {
                Some(w) if off(w.tenths) >= off(r.tenths) => Some(w),
                _ => Some(r),
            });
            let worst = worst.map_or("-".to_string(), |r| format!("{} at {}", degrees(r.tenths), r.clock));
            (Some(bad.len()), worst)
        }
        None => (None, "-".to_string()),
    };
    Line {
        cells: [
            unit.to_string(),
            date.to_string(),
            temps.len().to_string(),
            degrees(*temps.iter().min().unwrap()),
            degrees(*temps.iter().max().unwrap()),
            degrees(stats::mean(&temps)),
            degrees(stats::median(&temps)),
            out.map_or("-".to_string(), |n| n.to_string()),
        ],
        worst,
        out,
    }
}
