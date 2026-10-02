//! Race files (docs/race-file.md), clock times, the club's Portsmouth Numbers, and the table layout both
//! race-office tools print.

pub mod handicap;

use std::fmt;
use std::fs;
use std::path::Path;

/// A time of day, in seconds since midnight.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Clock(u32);

impl Clock {
    pub const fn from_seconds(seconds: u32) -> Clock {
        Clock(seconds)
    }

    pub fn seconds(self) -> u32 {
        self.0
    }

    /// Parses `HH:MM:SS`, 24-hour, two digits each.
    pub fn parse(text: &str) -> Option<Clock> {
        let b = text.as_bytes();
        if b.len() != 8 || b[2] != b':' || b[5] != b':' {
            return None;
        }
        let two = |i: usize| -> Option<u32> {
            let (hi, lo) = (b[i], b[i + 1]);
            (hi.is_ascii_digit() && lo.is_ascii_digit()).then(|| u32::from(hi - b'0') * 10 + u32::from(lo - b'0'))
        };
        let (h, m, s) = (two(0)?, two(3)?, two(6)?);
        (h < 24 && m < 60 && s < 60).then_some(Clock(h * 3600 + m * 60 + s))
    }

    /// The clock time `seconds` later, or None if that is past midnight.
    pub fn plus(self, seconds: u32) -> Option<Clock> {
        let t = self.0.checked_add(seconds)?;
        (t < 86_400).then_some(Clock(t))
    }

    /// The clock time `seconds` earlier, or None if that is before midnight.
    pub fn minus(self, seconds: u32) -> Option<Clock> {
        self.0.checked_sub(seconds).map(Clock)
    }
}

impl fmt::Display for Clock {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:02}:{:02}:{:02}", self.0 / 3600, self.0 / 60 % 60, self.0 % 60)
    }
}

/// A duration in seconds as `H:MM:SS`.
pub fn duration(seconds: u32) -> String {
    format!("{}:{:02}:{:02}", seconds / 3600, seconds / 60 % 60, seconds % 60)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Finish {
    Time(Clock),
    Dnf,
    Dns,
    /// No finish written yet: the race hasn't been sailed, or is still on.
    NotYet,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Boat {
    /// Line number in the race file, for messages.
    pub line: usize,
    pub sail: String,
    pub helm: String,
    pub class: String,
    pub finish: Finish,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Race {
    pub name: String,
    pub start: Clock,
    pub boats: Vec<Boat>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParseError {
    /// 0 when the problem is the file as a whole.
    pub line: usize,
    pub message: String,
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.line == 0 {
            write!(f, "{}", self.message)
        } else {
            write!(f, "line {}: {}", self.line, self.message)
        }
    }
}

impl std::error::Error for ParseError {}

fn error(line: usize, message: impl Into<String>) -> ParseError {
    ParseError { line, message: message.into() }
}

/// Parses a race file (docs/race-file.md).
pub fn parse(text: &str) -> Result<Race, ParseError> {
    let mut name: Option<String> = None;
    let mut start: Option<Clock> = None;
    let mut boats: Vec<Boat> = Vec::new();
    for (i, raw) in text.lines().enumerate() {
        let n = i + 1;
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let (keyword, rest) = match line.split_once(char::is_whitespace) {
            Some((k, r)) => (k, r.trim()),
            None => (line, ""),
        };
        match keyword {
            "race" if name.is_some() => return Err(error(n, "second race line")),
            "race" if rest.is_empty() => return Err(error(n, "race needs a name")),
            "race" => name = Some(rest.to_string()),
            "start" if start.is_some() => return Err(error(n, "second start line")),
            "start" => start = Some(Clock::parse(rest).ok_or_else(|| error(n, format!("bad start time {rest:?}")))?),
            "boat" => {
                let boat = parse_boat(n, rest)?;
                if let Some(other) = boats.iter().find(|b| b.sail == boat.sail) {
                    return Err(error(n, format!("sail {} is already entered on line {}", boat.sail, other.line)));
                }
                boats.push(boat);
            }
            other => return Err(error(n, format!("unknown line {other:?}"))),
        }
    }
    let name = name.ok_or_else(|| error(0, "no race line"))?;
    let start = start.ok_or_else(|| error(0, "no start line"))?;
    for b in &boats {
        if let Finish::Time(t) = b.finish {
            if t <= start {
                return Err(error(b.line, format!("finish {t} is not after the start {start}")));
            }
        }
    }
    Ok(Race { name, start, boats })
}

fn parse_boat(n: usize, rest: &str) -> Result<Boat, ParseError> {
    let fields: Vec<&str> = rest.split('|').map(str::trim).collect();
    if !(3..=4).contains(&fields.len()) {
        return Err(error(n, "a boat line is: boat SAIL | HELM | CLASS [| FINISH]"));
    }
    let sail = fields[0];
    if sail.is_empty() || sail.len() > 6 || !sail.bytes().all(|c| c.is_ascii_digit()) {
        return Err(error(n, format!("bad sail number {sail:?}")));
    }
    if fields[1].is_empty() {
        return Err(error(n, format!("sail {sail} has no helm")));
    }
    if fields[2].is_empty() {
        return Err(error(n, format!("sail {sail} has no class")));
    }
    let finish = match fields.get(3).copied().unwrap_or("") {
        "" => Finish::NotYet,
        "DNF" => Finish::Dnf,
        "DNS" => Finish::Dns,
        t => Finish::Time(Clock::parse(t).ok_or_else(|| error(n, format!("bad finish {t:?}")))?),
    };
    Ok(Boat { line: n, sail: sail.to_string(), helm: fields[1].to_string(), class: fields[2].to_string(), finish })
}

/// Reads and parses a race file; the message names the file.
pub fn read(path: &Path) -> Result<Race, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("cannot read {}: {e}", path.display()))?;
    parse(&text).map_err(|e| format!("{}: {e}", path.display()))
}

/// Lays out rows (the first is the header) in columns separated by two spaces, each as wide as its widest
/// cell, counted in characters. Columns whose `right` flag is set are right-aligned. Trailing spaces are
/// trimmed, and every line ends with a newline.
pub fn layout(rows: &[Vec<String>], right: &[bool]) -> String {
    let columns = rows.iter().map(Vec::len).max().unwrap_or(0);
    let widths: Vec<usize> = (0..columns)
        .map(|c| rows.iter().filter_map(|r| r.get(c)).map(|s| s.chars().count()).max().unwrap_or(0))
        .collect();
    let mut out = String::new();
    for row in rows {
        let mut line = String::new();
        for (c, cell) in row.iter().enumerate() {
            if c > 0 {
                line.push_str("  ");
            }
            let pad = " ".repeat(widths[c] - cell.chars().count());
            if right.get(c).copied().unwrap_or(false) {
                line.push_str(&pad);
                line.push_str(cell);
            } else {
                line.push_str(cell);
                line.push_str(&pad);
            }
        }
        out.push_str(line.trim_end());
        out.push('\n');
    }
    out
}
