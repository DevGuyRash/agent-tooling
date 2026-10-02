//! The loggers' exports: one reading per line, `TIME<TAB>UNIT<TAB>TEMPERATURE` (docs/format.md).

use crate::Failure;

/// One reading, as the logger wrote it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Reading {
    /// `YYYY-MM-DD`, UTC.
    pub date: String,
    /// `HH:MM`, UTC.
    pub clock: String,
    pub unit: String,
    /// Tenths of a degree Celsius.
    pub tenths: i32,
}

/// Every file's readings, in order (files as given, lines as written); the first problem stops it.
pub fn read_all(paths: &[String]) -> Result<Vec<Reading>, Failure> {
    let mut all = Vec::new();
    for path in paths {
        all.extend(read_file(path).map_err(Failure::Data)?);
    }
    Ok(all)
}

/// One file's readings, or a message naming the file (and the line, for a bad line).
pub fn read_file(path: &str) -> Result<Vec<Reading>, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{path}: cannot read: {}", reason(&e)))?;
    parse(&text).map_err(|(line, msg)| format!("{path}:{line}: {msg}"))
}

fn reason(e: &std::io::Error) -> String {
    match e.kind() {
        std::io::ErrorKind::NotFound => "no such file".into(),
        std::io::ErrorKind::InvalidData => "not UTF-8 text".into(),
        _ => e.to_string(),
    }
}

/// The readings in an export's text, or (line number, what is wrong) for the first bad line.
pub fn parse(text: &str) -> Result<Vec<Reading>, (usize, String)> {
    let mut out = Vec::new();
    for (i, line) in text.lines().enumerate() {
        if line.trim().is_empty() || line.starts_with('#') {
            continue;
        }
        let fields: Vec<&str> = line.split('\t').collect();
        let [stamp, unit, temp] = fields[..] else {
            return Err((i + 1, "expected time, unit, and temperature separated by tabs".into()));
        };
        let Some((date, clock)) = split_stamp(stamp) else {
            return Err((i + 1, format!("bad time {stamp:?} (want YYYY-MM-DDTHH:MMZ)")));
        };
        if unit.trim().is_empty() || unit.trim() != unit {
            return Err((i + 1, format!("bad unit name {unit:?}")));
        }
        let Some(tenths) = parse_tenths(temp) else {
            return Err((i + 1, format!("bad temperature {temp:?} (want degrees with one decimal, like -18.5)")));
        };
        out.push(Reading { date: date.to_string(), clock: clock.to_string(), unit: unit.to_string(), tenths });
    }
    Ok(out)
}

/// `YYYY-MM-DDTHH:MMZ` as (`YYYY-MM-DD`, `HH:MM`).
fn split_stamp(stamp: &str) -> Option<(&str, &str)> {
    let (date, rest) = stamp.split_once('T')?;
    let clock = rest.strip_suffix('Z')?;
    let b = clock.as_bytes();
    let clock_ok = b.len() == 5
        && b[2] == b':'
        && [0, 1, 3, 4].iter().all(|&i| b[i].is_ascii_digit())
        && clock[..2].parse::<u32>().ok()? < 24
        && clock[3..].parse::<u32>().ok()? < 60;
    (is_date(date) && clock_ok).then_some((date, clock))
}

/// A real calendar date written `YYYY-MM-DD`.
pub fn is_date(text: &str) -> bool {
    let b = text.as_bytes();
    if b.len() != 10 || b[4] != b'-' || b[7] != b'-' {
        return false;
    }
    if ![0, 1, 2, 3, 5, 6, 8, 9].iter().all(|&i| b[i].is_ascii_digit()) {
        return false;
    }
    let year: u32 = text[..4].parse().unwrap_or(0);
    let month: u32 = text[5..7].parse().unwrap_or(0);
    let day: u32 = text[8..].parse().unwrap_or(0);
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if leap => 29,
        2 => 28,
        _ => return false,
    };
    (1..=days).contains(&day)
}

/// Degrees with exactly one decimal (`-18.5`, `3.0`) as tenths.
pub fn parse_tenths(text: &str) -> Option<i32> {
    let (negative, digits) = match text.strip_prefix('-') {
        Some(rest) => (true, rest),
        None => (false, text),
    };
    let (whole, frac) = digits.split_once('.')?;
    let ok = !whole.is_empty() && whole.len() <= 3 && frac.len() == 1;
    if !ok || !whole.bytes().chain(frac.bytes()).all(|c| c.is_ascii_digit()) {
        return None;
    }
    let value = whole.parse::<i32>().ok()? * 10 + frac.parse::<i32>().ok()?;
    Some(if negative { -value } else { value })
}

/// Tenths of a degree as degrees with one decimal: `-185` is `-18.5`, `-4` is `-0.4`.
pub fn degrees(tenths: i32) -> String {
    format!("{:.1}", f64::from(tenths) / 10.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tenths_round_trip() {
        for (text, tenths) in [("-18.5", -185), ("3.0", 30), ("-0.4", -4), ("0.0", 0), ("12.9", 129)] {
            assert_eq!(parse_tenths(text), Some(tenths), "{text}");
        }
        assert_eq!(degrees(-4), "-0.4");
        assert_eq!(degrees(-185), "-18.5");
        assert_eq!(degrees(0), "0.0");
    }

    #[test]
    fn rejects_other_temperatures() {
        for text in ["18", "-18.50", "+3.0", "3.", ".5", "1e1", "-", "4.a", "1000.0"] {
            assert_eq!(parse_tenths(text), None, "{text}");
        }
    }

    #[test]
    fn dates_and_times() {
        assert!(is_date("2024-02-29"));
        assert!(!is_date("2026-02-29"));
        assert!(!is_date("2026-9-21"));
        assert_eq!(split_stamp("2026-09-21T06:30Z"), Some(("2026-09-21", "06:30")));
        assert_eq!(split_stamp("2026-09-21T24:00Z"), None);
        assert_eq!(split_stamp("2026-09-21 06:30"), None);
    }

    #[test]
    fn bad_line_is_numbered() {
        let text = "# logger 4\n2026-09-21T06:00Z\tfrigo-lait\t3.1\n2026-09-21T06:30Z\tfrigo-lait\n";
        assert_eq!(parse(text).unwrap_err().0, 3);
    }
}
