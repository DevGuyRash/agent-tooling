//! Routing files (docs/routing.md): read a main file and its includes, check them, and work out where an
//! alert goes.

use std::collections::{BTreeMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

use history::{is_label_name, is_receiver_name, Time};

const DAYS: [&str; 7] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

/// The first problem in a set of routing files, as docs/routing.md writes it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error(pub String);

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

fn err<T>(at: &str, message: impl std::fmt::Display) -> Result<T, Error> {
    Err(Error(format!("{at}: {message}")))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Op {
    Equals,
    NotEquals,
    Matches,
    NotMatches,
}

#[derive(Debug, Clone)]
struct Matcher {
    label: String,
    op: Op,
    value: String,
}

#[derive(Debug, Clone)]
struct Window {
    days: [bool; 7],
    from: u32,
    to: u32,
}

#[derive(Debug, Default)]
struct Route {
    receiver: Option<(String, String)>, // (name, FILE:LINE)
    matchers: Vec<Matcher>,
    windows: Vec<Window>,
    cont: bool,
    children: Vec<usize>,
}

/// Everything a main routing file and its includes define.
#[derive(Debug)]
pub struct Routing {
    routes: Vec<Route>, // in the order their blocks were read; the root is routes[0]
}

/// A statement line: where it is, its text, and its words.
struct Line<'a> {
    at: String,
    text: &'a str,
    words: Vec<&'a str>,
}

fn lines<'a>(path: &str, text: &'a str) -> Vec<Line<'a>> {
    let mut out = Vec::new();
    for (i, raw) in text.split('\n').enumerate() {
        let raw = raw.strip_suffix('\r').unwrap_or(raw);
        let line = raw.trim_matches(|c| c == ' ' || c == '\t');
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let words = line.split([' ', '\t']).filter(|w| !w.is_empty()).collect();
        out.push(Line { at: format!("{path}:{}", i + 1), text: line, words });
    }
    out
}

enum Block {
    Receiver,
    Route(usize),
}

struct Loader {
    routes: Vec<Route>,
    receivers: BTreeMap<String, String>,
    uses: Vec<(String, String)>, // (name, FILE:LINE) of every route's receiver line, in the order read
    reading: Vec<PathBuf>,
    done: HashSet<PathBuf>,
}

fn read_text(path: &Path) -> Option<String> {
    fs::read_to_string(path).ok()
}

/// The PATH of an `include "PATH"` line.
fn include_path(text: &str) -> Option<&str> {
    let rest = text.strip_prefix("include")?;
    if !rest.starts_with([' ', '\t']) {
        return None;
    }
    let quoted = rest.trim_start_matches([' ', '\t']);
    let inner = quoted.strip_prefix('"')?.strip_suffix('"')?;
    (!inner.is_empty() && !inner.contains('"')).then_some(inner)
}

fn parse_days(text: &str) -> Option<[bool; 7]> {
    let mut days = [false; 7];
    for part in text.split(',') {
        let ends: Vec<&str> = part.split('-').collect();
        if ends.len() > 2 {
            return None;
        }
        let first = DAYS.iter().position(|d| *d == ends[0])?;
        let last = DAYS.iter().position(|d| *d == ends[ends.len() - 1])?;
        let mut day = first;
        loop {
            days[day] = true;
            if day == last {
                break;
            }
            day = (day + 1) % 7;
        }
    }
    Some(days)
}

fn parse_clock(text: &str) -> Option<(u32, u32)> {
    let b = text.as_bytes();
    if b.len() != 5 || b[2] != b':' || !text[..2].bytes().chain(text[3..].bytes()).all(|c| c.is_ascii_digit()) {
        return None;
    }
    Some((text[..2].parse().ok()?, text[3..].parse().ok()?))
}

fn parse_window(text: &str) -> Option<(u32, u32)> {
    let (from, to) = text.split_once('-')?;
    let (fh, fm) = parse_clock(from)?;
    let (th, tm) = parse_clock(to)?;
    if fh > 23 || fm > 59 || tm > 59 || th > 24 || (th == 24 && tm != 0) {
        return None;
    }
    let (from, to) = (fh * 60 + fm, th * 60 + tm);
    (from < to).then_some((from, to))
}

impl Loader {
    fn read_file(
        &mut self,
        path: &str,
        text: &str,
        host: Option<usize>,
        main: bool,
        included_at: Option<(&str, &str)>,
    ) -> Result<(), Error> {
        let real = fs::canonicalize(path).unwrap_or_else(|_| PathBuf::from(path));
        self.reading.push(real.clone());
        let mut stack: Vec<(Block, String)> = Vec::new();
        for line in lines(path, text) {
            let at = line.at.as_str();
            let words = &line.words;
            let first = words[0];
            let allowed: &[&str] = match stack.last() {
                None => &["include", "receiver", "route"],
                Some((Block::Receiver, _)) => &["page", "chat", "ticket", "}"],
                Some((Block::Route(_), _)) => &["receiver", "match", "during", "continue", "route", "include", "}"],
            };
            if !allowed.contains(&first) {
                return err(at, format!("unexpected \"{first}\""));
            }
            let current = match stack.last() {
                Some((Block::Route(r), _)) => Some(*r),
                _ => None,
            };
            match first {
                "}" => {
                    if words.len() != 1 {
                        return err(at, "expected: }");
                    }
                    let (block, opened) = stack.pop().expect("a block is open");
                    if let Block::Route(r) = block {
                        if r == 0 && self.routes[0].receiver.is_none() {
                            return err(&opened, "the root route has no receiver");
                        }
                    }
                }
                "include" => {
                    let Some(written) = include_path(line.text) else {
                        return err(at, "expected: include \"PATH\"");
                    };
                    self.include(path, at, written, current)?;
                }
                "receiver" if stack.is_empty() => {
                    if words.len() != 3 || words[2] != "{" {
                        return err(at, "expected: receiver NAME {");
                    }
                    let name = words[1];
                    if !is_receiver_name(name) {
                        return err(at, format!("bad receiver name \"{name}\""));
                    }
                    if let Some(first_at) = self.receivers.get(name) {
                        return err(at, format!("receiver \"{name}\" is already defined at {first_at}"));
                    }
                    self.receivers.insert(name.to_string(), at.to_string());
                    stack.push((Block::Receiver, at.to_string()));
                }
                "route" => {
                    if words[..] != ["route", "{"] {
                        return err(at, "expected: route {");
                    }
                    let parent = match current {
                        Some(r) => Some(r),
                        None if main => {
                            if !self.routes.is_empty() {
                                return err(at, "second root route");
                            }
                            None
                        }
                        None => match host {
                            Some(h) => Some(h),
                            None => {
                                let (inc_at, written) = included_at.expect("an included file");
                                return err(inc_at, format!("\"{written}\" has routes; include it inside a route"));
                            }
                        },
                    };
                    let id = self.routes.len();
                    self.routes.push(Route::default());
                    if let Some(p) = parent {
                        self.routes[p].children.push(id);
                    }
                    stack.push((Block::Route(id), at.to_string()));
                }
                "page" | "chat" | "ticket" => {
                    if words.len() != 2 {
                        let form = match first {
                            "page" => "page SCHEDULE",
                            "chat" => "chat CHANNEL",
                            _ => "ticket QUEUE",
                        };
                        return err(at, format!("expected: {form}"));
                    }
                }
                _ => self.route_line(current.expect("inside a route"), at, words)?,
            }
        }
        if let Some((_, opened)) = stack.last() {
            return err(opened, "block is not closed");
        }
        self.reading.pop();
        self.done.insert(real);
        Ok(())
    }

    fn route_line(&mut self, r: usize, at: &str, words: &[&str]) -> Result<(), Error> {
        let first = words[0];
        if r == 0 && matches!(first, "match" | "during" | "continue") {
            return err(at, format!("the root route cannot have \"{first}\""));
        }
        let route = &mut self.routes[r];
        match first {
            "receiver" => {
                if words.len() != 2 {
                    return err(at, "expected: receiver NAME");
                }
                if route.receiver.is_some() {
                    return err(at, "\"receiver\" given twice in one route");
                }
                route.receiver = Some((words[1].to_string(), at.to_string()));
                self.uses.push((words[1].to_string(), at.to_string()));
            }
            "match" => {
                let [_, label, op, value] = words[..] else {
                    return err(at, "expected: match LABEL OP VALUE");
                };
                if !is_label_name(label) {
                    return err(at, format!("bad label \"{label}\""));
                }
                let op = match op {
                    "=" => Op::Equals,
                    "!=" => Op::NotEquals,
                    "~" => Op::Matches,
                    "!~" => Op::NotMatches,
                    _ => return err(at, format!("bad operator \"{op}\"")),
                };
                route.matchers.push(Matcher { label: label.to_string(), op, value: value.to_string() });
            }
            "during" => {
                let [_, days, window] = words[..] else {
                    return err(at, "expected: during DAYS FROM-TO");
                };
                let Some(days_set) = parse_days(days) else {
                    return err(at, format!("bad days \"{days}\""));
                };
                let Some((from, to)) = parse_window(window) else {
                    return err(at, format!("bad time window \"{window}\""));
                };
                route.windows.push(Window { days: days_set, from, to });
            }
            _ => {
                if words.len() != 1 {
                    return err(at, "expected: continue");
                }
                if route.cont {
                    return err(at, "\"continue\" given twice in one route");
                }
                route.cont = true;
            }
        }
        Ok(())
    }

    fn include(&mut self, path: &str, at: &str, written: &str, host: Option<usize>) -> Result<(), Error> {
        let dir = Path::new(path).parent().unwrap_or(Path::new(""));
        let target = dir.join(written);
        let shown = target.to_string_lossy().into_owned();
        let real = fs::canonicalize(&target).ok();
        if let Some(real) = &real {
            if self.reading.contains(real) {
                return err(at, format!("include cycle at \"{written}\""));
            }
            if self.done.contains(real) {
                return Ok(());
            }
        }
        let Some(text) = read_text(&target) else {
            return err(at, format!("cannot read \"{written}\""));
        };
        self.read_file(&shown, &text, host, false, Some((at, written)))
    }
}

impl Routing {
    /// Read the main file at `path` and everything it includes.
    pub fn load(path: &str) -> Result<Routing, Error> {
        let Some(text) = read_text(Path::new(path)) else {
            return err(path, "cannot read");
        };
        let mut loader = Loader {
            routes: Vec::new(),
            receivers: BTreeMap::new(),
            uses: Vec::new(),
            reading: Vec::new(),
            done: HashSet::new(),
        };
        loader.read_file(path, &text, None, true, None)?;
        if loader.routes.is_empty() {
            return err(path, "no root route");
        }
        for (name, at) in &loader.uses {
            if !loader.receivers.contains_key(name) {
                return err(at, format!("unknown receiver \"{name}\""));
            }
        }
        Ok(Routing { routes: loader.routes })
    }

    /// The receivers an alert with these labels, firing at `time`, goes to, in the order routes took it.
    pub fn receivers_for(&self, labels: &[(&str, &str)], time: &Time) -> Vec<String> {
        let mut out = Vec::new();
        self.take(0, None, labels, time, &mut out);
        out
    }

    fn take(&self, r: usize, inherited: Option<&str>, labels: &[(&str, &str)], time: &Time, out: &mut Vec<String>) {
        let route = &self.routes[r];
        let receiver = route.receiver.as_ref().map(|(n, _)| n.as_str()).or(inherited).expect("the root has a receiver");
        let mut taken = false;
        for &child in &route.children {
            if self.matches(child, labels, time) {
                self.take(child, Some(receiver), labels, time, out);
                taken = true;
                if !self.routes[child].cont {
                    break;
                }
            }
        }
        if !taken && !out.iter().any(|o| o == receiver) {
            out.push(receiver.to_string());
        }
    }

    fn matches(&self, r: usize, labels: &[(&str, &str)], time: &Time) -> bool {
        let route = &self.routes[r];
        let held = route.matchers.iter().all(|m| {
            let value = labels.iter().find(|(n, _)| *n == m.label).map(|(_, v)| *v).unwrap_or("");
            match m.op {
                Op::Equals => value == m.value,
                Op::NotEquals => value != m.value,
                Op::Matches => pattern_matches(&m.value, value),
                Op::NotMatches => !pattern_matches(&m.value, value),
            }
        });
        if !held {
            return false;
        }
        if route.windows.is_empty() {
            return true;
        }
        let (day, minute) = (time.weekday(), time.minute_of_day());
        route.windows.iter().any(|w| w.days[day] && w.from <= minute && minute < w.to)
    }
}

/// Whether `value` matches `pattern` as a whole, `*` standing for any run of characters.
pub fn pattern_matches(pattern: &str, value: &str) -> bool {
    let pieces: Vec<&str> = pattern.split('*').collect();
    if pieces.len() == 1 {
        return pattern == value;
    }
    let (head, tail) = (pieces[0], pieces[pieces.len() - 1]);
    if value.len() < head.len() + tail.len() || !value.starts_with(head) || !value.ends_with(tail) {
        return false;
    }
    let mut rest = &value[head.len()..value.len() - tail.len()];
    for piece in &pieces[1..pieces.len() - 1] {
        match rest.find(piece) {
            Some(i) => rest = &rest[i + piece.len()..],
            None => return false,
        }
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn patterns() {
        assert!(pattern_matches("db-*", "db-"));
        assert!(pattern_matches("*Latency", "ApiLatency"));
        assert!(pattern_matches("a*b*c", "aXbYbc"));
        assert!(pattern_matches("*", ""));
        assert!(!pattern_matches("db-*", "mydb-1"));
        assert!(!pattern_matches("a*a", "a"));
        assert!(!pattern_matches("checkout", "checkout-eu"));
    }

    #[test]
    fn days_and_windows() {
        assert_eq!(parse_days("fri-mon"), Some([true, false, false, false, true, true, true]));
        assert_eq!(parse_days("mon-thu,sat"), Some([true, true, true, true, false, true, false]));
        assert_eq!(parse_days("mon,"), None);
        assert_eq!(parse_days("weekend"), None);
        assert_eq!(parse_window("00:00-24:00"), Some((0, 1440)));
        assert_eq!(parse_window("17:00-09:00"), None);
        assert_eq!(parse_window("9:00-17:00"), None);
        assert_eq!(parse_window("24:00-24:00"), None);
    }

    #[test]
    fn include_lines() {
        assert_eq!(include_path("include \"teams/a.routes\""), Some("teams/a.routes"));
        assert_eq!(include_path("include\t \"a b.routes\""), Some("a b.routes"));
        assert_eq!(include_path("include teams/a.routes"), None);
        assert_eq!(include_path("include \"\""), None);
        assert_eq!(include_path("include\"a\""), None);
    }
}
