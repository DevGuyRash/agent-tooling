//! The morning clash list (docs/clashes.md).

use booking::{format_clock, normalize_facility, same_facility, Booking, Status};
use std::fmt::Write;

/// Every pair of bookings that clash, as (earlier, later) positions in the export, in export order.
///
/// The comparisons are spread over every core: thread t takes the bookings i with i % threads == t (which
/// balances the shrinking rows), and the pairs are put back in export order at the end.
pub fn find_clashes(bookings: &[Booking]) -> Vec<(usize, usize)> {
    let threads = std::thread::available_parallelism().map_or(1, |n| n.get());
    let mut pairs: Vec<(usize, usize)> = std::thread::scope(|scope| {
        let workers: Vec<_> = (0..threads)
            .map(|t| {
                scope.spawn(move || {
                    let mut found = Vec::new();
                    for i in (t..bookings.len()).step_by(threads) {
                        for j in i + 1..bookings.len() {
                            if clash(&bookings[i], &bookings[j]) {
                                found.push((i, j));
                            }
                        }
                    }
                    found
                })
            })
            .collect();
        workers
            .into_iter()
            .flat_map(|w| w.join().unwrap())
            .collect()
    });
    pairs.sort_unstable();
    pairs
}

fn clash(a: &Booking, b: &Booking) -> bool {
    a.status != Status::Cancelled
        && b.status != Status::Cancelled
        && same_facility(&a.facility, &b.facility)
        && a.date == b.date
        && a.start < b.end
        && b.start < a.end
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
