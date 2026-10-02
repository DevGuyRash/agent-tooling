//! The morning clash list (docs/clashes.md).

use booking::{format_clock, normalize_facility, Booking, Date, Status};
use std::collections::HashMap;
use std::fmt::Write;

/// Every pair of bookings that clash, as (earlier, later) positions in the export, in export order.
///
/// Bookings on different dates never clash, so only bookings on the same date are compared, with each
/// facility code normalized once up front.
pub fn find_clashes(bookings: &[Booking]) -> Vec<(usize, usize)> {
    let facilities: Vec<String> = bookings
        .iter()
        .map(|b| normalize_facility(&b.facility))
        .collect();
    let mut dates: HashMap<Date, Vec<usize>> = HashMap::new();
    for (i, b) in bookings.iter().enumerate() {
        if b.status != Status::Cancelled {
            dates.entry(b.date).or_default().push(i);
        }
    }
    let mut pairs = Vec::new();
    for day in dates.values() {
        for (k, &i) in day.iter().enumerate() {
            let a = &bookings[i];
            for &j in &day[k + 1..] {
                let b = &bookings[j];
                if a.start < b.end && b.start < a.end && facilities[i] == facilities[j] {
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
