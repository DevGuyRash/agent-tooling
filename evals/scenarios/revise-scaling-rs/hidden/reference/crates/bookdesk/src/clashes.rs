//! The morning clash list (docs/clashes.md).

use booking::{format_clock, normalize_facility, Booking, Date, Status};
use std::collections::HashMap;
use std::fmt::Write;

/// Every pair of bookings that clash, as (earlier, later) positions in the export, in export order.
///
/// Only bookings for the same facility on the same date can clash, so the bookings are grouped by those
/// first. Within a group, taken in order of start time, a booking clashes with exactly the earlier-starting
/// bookings that are still running when it starts.
pub fn find_clashes(bookings: &[Booking]) -> Vec<(usize, usize)> {
    let mut groups: HashMap<(String, Date), Vec<usize>> = HashMap::new();
    for (i, b) in bookings.iter().enumerate() {
        if b.status != Status::Cancelled {
            groups
                .entry((normalize_facility(&b.facility), b.date))
                .or_default()
                .push(i);
        }
    }
    let mut pairs = Vec::new();
    let mut running: Vec<usize> = Vec::new();
    for mut group in groups.into_values() {
        group.sort_by_key(|&i| bookings[i].start);
        running.clear();
        for i in group {
            let b = &bookings[i];
            running.retain(|&r| bookings[r].end > b.start);
            pairs.extend(running.iter().map(|&r| (r.min(i), r.max(i))));
            running.push(i);
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
