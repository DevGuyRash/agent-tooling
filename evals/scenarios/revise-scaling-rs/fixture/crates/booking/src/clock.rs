//! Dates and clock times as the export writes them.

use std::fmt;

/// A calendar date (YYYY-MM-DD in the export). Dates order as they read.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Date {
    pub year: u16,
    pub month: u8,
    pub day: u8,
}

impl Date {
    pub fn parse(text: &str) -> Option<Date> {
        let b = text.as_bytes();
        if b.len() != 10 || b[4] != b'-' || b[7] != b'-' {
            return None;
        }
        let year: u16 = digits(&text[0..4])?;
        let month: u8 = digits(&text[5..7])?;
        let day: u8 = digits(&text[8..10])?;
        let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
        let days = match month {
            1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
            4 | 6 | 9 | 11 => 30,
            2 if leap => 29,
            2 => 28,
            _ => return None,
        };
        (day >= 1 && day <= days).then_some(Date { year, month, day })
    }
}

impl fmt::Display for Date {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:04}-{:02}-{:02}", self.year, self.month, self.day)
    }
}

fn digits<T: std::str::FromStr>(text: &str) -> Option<T> {
    if text.bytes().all(|c| c.is_ascii_digit()) {
        text.parse().ok()
    } else {
        None
    }
}

/// HH:MM, 24-hour, as minutes after midnight.
pub fn parse_clock(text: &str) -> Option<u16> {
    let b = text.as_bytes();
    if b.len() != 5 || b[2] != b':' {
        return None;
    }
    let h: u16 = digits(&text[0..2])?;
    let m: u16 = digits(&text[3..5])?;
    (h < 24 && m < 60).then_some(h * 60 + m)
}

/// Minutes after midnight as HH:MM.
pub fn format_clock(minutes: u16) -> String {
    format!("{:02}:{:02}", minutes / 60, minutes % 60)
}

/// A number of minutes as hours and minutes (H:MM), for totals.
pub fn format_duration(minutes: u64) -> String {
    format!("{}:{:02}", minutes / 60, minutes % 60)
}
