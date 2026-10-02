//! The city booking system's nightly export of upcoming bookings (docs/export.md): reading it into
//! bookings, and every problem with it, by line.

mod clock;
mod facility;

use std::fmt;

pub use clock::{format_clock, format_duration, parse_clock, Date};
pub use facility::{centre, normalize_facility, same_facility};

pub const HEADER: &str = "ref,facility,date,start,end,status,booked_by";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Status {
    Confirmed,
    Provisional,
    Cancelled,
}

#[derive(Debug, Clone)]
pub struct Booking {
    /// The line of the export it came from (the header is line 1).
    pub line: usize,
    pub reference: String,
    /// The facility code as written in the export.
    pub facility: String,
    pub date: Date,
    /// Minutes after midnight.
    pub start: u16,
    pub end: u16,
    pub status: Status,
    pub booked_by: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Problem {
    pub line: usize,
    pub message: String,
}

impl fmt::Display for Problem {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

/// Every booking in the export, or every problem with it (at most one per line), in line order.
pub fn parse_export(text: &str) -> Result<Vec<Booking>, Vec<Problem>> {
    let mut lines = text.split('\n').map(|l| l.strip_suffix('\r').unwrap_or(l));
    if lines.next() != Some(HEADER) {
        return Err(vec![Problem {
            line: 1,
            message: format!("expected the header {HEADER}"),
        }]);
    }
    let mut bookings: Vec<Booking> = Vec::new();
    let mut problems = Vec::new();
    for (i, text) in lines.enumerate() {
        let line = i + 2;
        if text.is_empty() {
            continue;
        }
        match parse_line(line, text) {
            Err(message) => problems.push(Problem { line, message }),
            Ok(booking) => {
                // A reference is given once, when the booking is made; seeing it again means the export
                // went wrong. When it does, a page of the export comes out twice in a row, so a repeat is
                // never far from the first; looking back over the last 64 bookings finds it.
                if let Some(earlier) = bookings
                    .iter()
                    .rev()
                    .take(64)
                    .find(|b| b.reference == booking.reference)
                {
                    problems.push(Problem {
                        line,
                        message: format!(
                            "booking {} is already on line {}",
                            booking.reference, earlier.line
                        ),
                    });
                } else {
                    bookings.push(booking);
                }
            }
        }
    }
    if problems.is_empty() {
        Ok(bookings)
    } else {
        Err(problems)
    }
}

fn parse_line(line: usize, text: &str) -> Result<Booking, String> {
    let fields: Vec<&str> = text.split(',').collect();
    let [reference, facility, date, start, end, status, booked_by] = fields[..] else {
        return Err(format!("expected 7 fields, found {}", fields.len()));
    };
    if reference.is_empty() || reference.contains(char::is_whitespace) {
        return Err(format!("bad booking reference '{reference}'"));
    }
    if normalize_facility(facility).is_empty() {
        return Err(format!("bad facility '{facility}'"));
    }
    let date = Date::parse(date).ok_or_else(|| format!("bad date '{date}'"))?;
    let start_at = parse_clock(start).ok_or_else(|| format!("bad time '{start}'"))?;
    let end_at = parse_clock(end).ok_or_else(|| format!("bad time '{end}'"))?;
    if end_at <= start_at {
        return Err(format!("ends at {end}, not after it starts at {start}"));
    }
    let status = match status {
        "confirmed" => Status::Confirmed,
        "provisional" => Status::Provisional,
        "cancelled" => Status::Cancelled,
        other => return Err(format!("unknown status '{other}'")),
    };
    Ok(Booking {
        line,
        reference: reference.to_string(),
        facility: facility.to_string(),
        date,
        start: start_at,
        end: end_at,
        status,
        booked_by: booked_by.to_string(),
    })
}
