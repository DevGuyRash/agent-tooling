//! The morning clash list (docs/clashes.md).

use booking::{format_clock, normalize_facility, Booking, Date, Status};
use std::collections::BTreeMap;
use std::fmt::Write;

/// Every pair of bookings that clash, as (earlier, later) positions in the export, in export order.
///
/// Only bookings for the same facility on the same date can clash, and a facility has a handful of bookings
/// a day, so each facility-day's bookings are compared with each other only.
pub fn find_clashes(bookings: &[Booking]) -> Vec<(usize, usize)> {
    let mut days: BTreeMap<(Date, String), Vec<usize>> = BTreeMap::new();
    for (i, b) in bookings.iter().enumerate() {
        if b.status != Status::Cancelled {
            days.entry((b.date, normalize_facility(&b.facility)))
                .or_default()
                .push(i);
        }
    }
    let mut pairs = Vec::new();
    for day in days.values() {
        for (k, &i) in day.iter().enumerate() {
            for &j in &day[k + 1..] {
                let (a, b) = (&bookings[i], &bookings[j]);
                if a.start < b.end && b.start < a.end {
                    pairs.push((i, j));
                }
            }
        }
    }
    pairs.sort_unstable();
    pairs
}

fn describe(b: &Booking) -> String {
    let provisional = if b.status == Status::Provisional {
        " (provisional)"
    } else {
        ""
    };
    format!(
        "{} {}-{} {}{}",
        b.reference,
        format_clock(b.start),
        format_clock(b.end),
        b.booked_by,
        provisional
    )
}

pub fn report(bookings: &[Booking], pairs: &[(usize, usize)]) -> String {
    let mut out = String::new();
    let mut facilities: Vec<String> = Vec::new();
    for &(i, j) in pairs {
        let (a, b) = (&bookings[i], &bookings[j]);
        let facility = normalize_facility(&a.facility);
        let _ = writeln!(
            out,
            "{facility}  {}  {}  {}",
            a.date,
            describe(a),
            describe(b)
        );
        if !facilities.contains(&facility) {
            facilities.push(facility);
        }
    }
    match (pairs.len(), facilities.len()) {
        (0, _) => out.push_str("no clashes\n"),
        (1, _) => out.push_str("1 clash on 1 facility\n"),
        (n, 1) => {
            let _ = writeln!(out, "{n} clashes on 1 facility");
        }
        (n, f) => {
            let _ = writeln!(out, "{n} clashes on {f} facilities");
        }
    }
    out
}
