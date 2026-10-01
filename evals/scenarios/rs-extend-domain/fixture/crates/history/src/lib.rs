//! The paging service's alert history exports: parse and check them (docs/history.md).

use std::fmt;

/// The header line every export starts with.
pub const HEADER: &str = "time\talert\treceivers\tlabels";

/// Days of the week, Monday first.
pub const WEEKDAYS: [&str; 7] = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

/// A moment in UTC, to the second. Times order chronologically.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Time {
    pub year: u16,
    pub month: u8,
    pub day: u8,
    pub hour: u8,
    pub minute: u8,
    pub second: u8,
}

fn is_leap(year: u16) -> bool {
    (year % 4 == 0 && year % 100 != 0) || year % 400 == 0
}

fn days_in_month(year: u16, month: u8) -> u8 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if is_leap(year) => 29,
        2 => 28,
        _ => 0,
    }
}

/// The digits of `s` as a number, when `s` is exactly `len` ASCII digits.
fn digits(s: &str, len: usize) -> Option<u16> {
    if s.len() != len || !s.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    s.parse().ok()
}

impl Time {
    /// Parse `YYYY-MM-DDTHH:MM:SSZ`; None when the text is not in that form or names no real moment.
    pub fn parse(s: &str) -> Option<Time> {
        let b = s.as_bytes();
        if b.len() != 20 || b[4] != b'-' || b[7] != b'-' || b[10] != b'T' || b[13] != b':' || b[16] != b':' || b[19] != b'Z' {
            return None;
        }
        let t = Time {
            year: digits(&s[0..4], 4)?,
            month: digits(&s[5..7], 2)? as u8,
            day: digits(&s[8..10], 2)? as u8,
            hour: digits(&s[11..13], 2)? as u8,
            minute: digits(&s[14..16], 2)? as u8,
            second: digits(&s[17..19], 2)? as u8,
        };
        let valid = (1..=12).contains(&t.month)
            && t.day >= 1
            && t.day <= days_in_month(t.year, t.month)
            && t.hour < 24
            && t.minute < 60
            && t.second < 60;
        valid.then_some(t)
    }

    /// Days since 1970-01-01 (negative before it).
    pub fn days_since_epoch(&self) -> i64 {
        // Howard Hinnant's days_from_civil.
        let (m, d) = (i64::from(self.month), i64::from(self.day));
        let y = i64::from(self.year) - i64::from(m <= 2);
        let era = y.div_euclid(400);
        let yoe = y - era * 400;
        let doy = (153 * (m + if m > 2 { -3 } else { 9 }) + 2) / 5 + d - 1;
        let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
        era * 146_097 + doe - 719_468
    }

    /// The day of the week, 0 for Monday to 6 for Sunday.
    pub fn weekday(&self) -> usize {
        // 1970-01-01 was a Thursday.
        (self.days_since_epoch() + 3).rem_euclid(7) as usize
    }

    /// Minutes since midnight.
    pub fn minute_of_day(&self) -> u32 {
        u32::from(self.hour) * 60 + u32::from(self.minute)
    }

    /// The date, `YYYY-MM-DD`.
    pub fn date(&self) -> String {
        format!("{:04}-{:02}-{:02}", self.year, self.month, self.day)
    }
}

impl fmt::Display for Time {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}T{:02}:{:02}:{:02}Z", self.date(), self.hour, self.minute, self.second)
    }
}

/// One alert the paging service delivered.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Alert {
    /// Its line in the export, counting from 1.
    pub line: usize,
    pub time: Time,
    pub name: String,
    /// The receivers it went to, as listed.
    pub receivers: Vec<String>,
    /// Its labels, as listed.
    pub labels: Vec<(String, String)>,
}

impl Alert {
    /// The value of a label, if the alert has it.
    pub fn label(&self, name: &str) -> Option<&str> {
        self.labels.iter().find(|(n, _)| n == name).map(|(_, v)| v.as_str())
    }
}

/// A whole export, alerts in file order.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct History {
    pub alerts: Vec<Alert>,
}

impl History {
    /// When the earliest alert fired.
    pub fn first(&self) -> Option<Time> {
        self.alerts.iter().map(|a| a.time).min()
    }

    /// When the latest alert fired.
    pub fn last(&self) -> Option<Time> {
        self.alerts.iter().map(|a| a.time).max()
    }
}

/// The first problem in an export.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error {
    pub line: usize,
    pub message: String,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "line {}: {}", self.line, self.message)
    }
}

impl std::error::Error for Error {}

fn fail<T>(line: usize, message: String) -> Result<T, Error> {
    Err(Error { line, message })
}

/// A receiver name: lowercase letters, digits, and '-', starting with a letter or digit.
pub fn is_receiver_name(s: &str) -> bool {
    let mut chars = s.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_lowercase() || c.is_ascii_digit())
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
}

/// A label name: lowercase letters, digits, and '_', not starting with a digit.
pub fn is_label_name(s: &str) -> bool {
    let mut chars = s.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_lowercase() || c == '_')
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
}

fn is_alert_name(s: &str) -> bool {
    !s.is_empty() && s.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
}

fn receivers(field: &str, line: usize) -> Result<Vec<String>, Error> {
    let mut out: Vec<String> = Vec::new();
    for name in field.split(',') {
        if !is_receiver_name(name) || out.iter().any(|r| r == name) {
            return fail(line, format!("bad receivers \"{field}\""));
        }
        out.push(name.to_string());
    }
    Ok(out)
}

fn labels(field: &str, line: usize) -> Result<Vec<(String, String)>, Error> {
    let mut out: Vec<(String, String)> = Vec::new();
    if field == "-" {
        return Ok(out);
    }
    for item in field.split(',') {
        let Some((name, value)) = item.split_once('=') else {
            return fail(line, format!("bad label \"{item}\""));
        };
        if !is_label_name(name) || value.is_empty() || value.contains(' ') {
            return fail(line, format!("bad label \"{item}\""));
        }
        if name == "alertname" {
            return fail(line, "label \"alertname\" is reserved".to_string());
        }
        if out.iter().any(|(n, _)| n == name) {
            return fail(line, format!("label \"{name}\" given twice"));
        }
        out.push((name.to_string(), value.to_string()));
    }
    Ok(out)
}

/// Parse a whole export.
pub fn parse(text: &str) -> Result<History, Error> {
    let mut lines = text.split('\n').map(|l| l.strip_suffix('\r').unwrap_or(l));
    if lines.next() != Some(HEADER) {
        return fail(1, "bad header".to_string());
    }
    let mut history = History::default();
    for (i, line) in lines.enumerate() {
        let number = i + 2;
        if line.is_empty() {
            continue;
        }
        let fields: Vec<&str> = line.split('\t').collect();
        if fields.len() != 4 {
            return fail(number, format!("expected 4 fields, found {}", fields.len()));
        }
        let Some(time) = Time::parse(fields[0]) else {
            return fail(number, format!("bad time \"{}\"", fields[0]));
        };
        if !is_alert_name(fields[1]) {
            return fail(number, format!("bad alert name \"{}\"", fields[1]));
        }
        history.alerts.push(Alert {
            line: number,
            time,
            name: fields[1].to_string(),
            receivers: receivers(fields[2], number)?,
            labels: labels(fields[3], number)?,
        });
    }
    Ok(history)
}
