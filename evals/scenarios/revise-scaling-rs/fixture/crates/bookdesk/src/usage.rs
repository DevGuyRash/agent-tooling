//! Hours booked per facility and centre (cancelled bookings left out).

use booking::{centre, format_duration, normalize_facility, Booking, Status};
use std::collections::BTreeMap;
use std::fmt::Write;

pub fn report(bookings: &[Booking], only_centre: Option<&str>) -> String {
    let only = only_centre.map(normalize_facility);
    let mut minutes: BTreeMap<String, u64> = BTreeMap::new();
    for b in bookings {
        if b.status == Status::Cancelled {
            continue;
        }
        let code = normalize_facility(&b.facility);
        if only.as_deref().is_some_and(|c| centre(&code) != c) {
            continue;
        }
        *minutes.entry(code).or_default() += u64::from(b.end - b.start);
    }
    let mut out = String::new();
    let mut all = 0;
    let mut current: Option<(String, u64)> = None;
    for (code, &m) in &minutes {
        let c = centre(code).to_string();
        if current.as_ref().is_some_and(|(name, _)| *name != c) {
            let (name, total) = current.take().unwrap();
            let _ = writeln!(
                out,
                "{:<16}{:>9}",
                format!("{name} total"),
                format_duration(total)
            );
        }
        current.get_or_insert((c, 0)).1 += m;
        all += m;
        let _ = writeln!(out, "{code:<16}{:>9}", format_duration(m));
    }
    if let Some((name, total)) = current {
        let _ = writeln!(
            out,
            "{:<16}{:>9}",
            format!("{name} total"),
            format_duration(total)
        );
    }
    let _ = writeln!(out, "{:<16}{:>9}", "all", format_duration(all));
    out
}
