//! Parse one access-log line written in logfmt by the edge proxies.

use std::collections::HashMap;
use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub struct ParseError(pub String);

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Request {
    pub ts: String,
    pub method: String,
    pub path: String,
    pub status: u32,
    pub dur_us: u128,
    pub bytes: u128,
}

fn is_sep(c: char) -> bool {
    c == ' ' || c == '\t'
}

/// The key=value pairs of a logfmt line; when a key repeats, the last value wins.
pub fn split_pairs(line: &str) -> Result<HashMap<String, String>, ParseError> {
    let chars: Vec<char> = line.chars().collect();
    let n = chars.len();
    let mut pairs = HashMap::new();
    let mut i = 0;
    while i < n {
        if is_sep(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        while i < n && chars[i] != '=' && !is_sep(chars[i]) {
            i += 1;
        }
        if i >= n || chars[i] != '=' {
            return Err(ParseError(format!("expected key=value at column {}", start + 1)));
        }
        let key: String = chars[start..i].iter().collect();
        if key.is_empty() {
            return Err(ParseError(format!("empty key at column {}", start + 1)));
        }
        i += 1;
        let value: String;
        if i < n && chars[i] == '"' {
            i += 1;
            let mut buf = String::new();
            loop {
                if i >= n {
                    return Err(ParseError(format!("unterminated quote in {key}")));
                }
                let c = chars[i];
                if c == '\\' {
                    if i + 1 >= n {
                        return Err(ParseError(format!("unterminated quote in {key}")));
                    }
                    buf.push(chars[i + 1]);
                    i += 2;
                } else if c == '"' {
                    i += 1;
                    break;
                } else {
                    buf.push(c);
                    i += 1;
                }
            }
            if i < n && !is_sep(chars[i]) {
                return Err(ParseError(format!("text after closing quote in {key}")));
            }
            value = buf;
        } else {
            let vstart = i;
            while i < n && !is_sep(chars[i]) {
                i += 1;
            }
            value = chars[vstart..i].iter().collect();
        }
        pairs.insert(key, value);
    }
    Ok(pairs)
}

fn all_digits(s: &str) -> bool {
    !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())
}

fn num(s: &str) -> u32 {
    s.parse().unwrap_or(0)
}

pub fn valid_timestamp(ts: &str) -> bool {
    let b = ts.as_bytes();
    if b.len() != 20 || !ts.is_ascii() {
        return false;
    }
    let shape_ok = b[4] == b'-' && b[7] == b'-' && b[10] == b'T' && b[13] == b':' && b[16] == b':' && b[19] == b'Z';
    let digits_ok = [0..4, 5..7, 8..10, 11..13, 14..16, 17..19].iter().all(|r| all_digits(&ts[r.clone()]));
    if !shape_ok || !digits_ok {
        return false;
    }
    let (month, day, hour, minute, second) = (num(&ts[5..7]), num(&ts[8..10]), num(&ts[11..13]), num(&ts[14..16]), num(&ts[17..19]));
    (1..=12).contains(&month) && (1..=31).contains(&day) && hour <= 23 && minute <= 59 && second <= 59
}

/// Duration text such as 12ms, 1.5s or 350us, as whole microseconds.
pub fn parse_duration(text: &str) -> Result<u128, ParseError> {
    let bad = || ParseError(format!("bad duration {}", py_repr(text)));
    let (number, scale) = if let Some(rest) = text.strip_suffix("us") {
        (rest, 0u32)
    } else if let Some(rest) = text.strip_suffix("ms") {
        (rest, 3)
    } else if let Some(rest) = text.strip_suffix('s') {
        (rest, 6)
    } else {
        return Err(bad());
    };
    let (whole, frac) = match number.split_once('.') {
        Some((w, f)) => {
            if !all_digits(f) {
                return Err(bad());
            }
            (w, f)
        }
        None => (number, ""),
    };
    if !all_digits(whole) || frac.len() > scale as usize {
        return Err(bad());
    }
    let whole: u128 = whole.parse().map_err(|_| bad())?;
    let mut frac_value: u128 = 0;
    if scale > 0 {
        let padded = format!("{frac:0<width$}", width = scale as usize);
        frac_value = padded.parse().map_err(|_| bad())?;
    }
    Ok(whole * 10u128.pow(scale) + frac_value)
}

/// Python's repr() of a string, as used in the error messages.
pub fn py_repr(s: &str) -> String {
    let quote = if s.contains('\'') && !s.contains('"') { '"' } else { '\'' };
    let mut out = String::new();
    out.push(quote);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => out.push_str(&format!("\\x{:02x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

/// Parse one line into a Request; the error says why it is not one.
pub fn parse_line(line: &str) -> Result<Request, ParseError> {
    let pairs = split_pairs(line)?;
    for key in ["ts", "method", "path", "status", "dur"] {
        if !pairs.contains_key(key) {
            return Err(ParseError(format!("missing {key}")));
        }
    }
    let ts = &pairs["ts"];
    if !valid_timestamp(ts) {
        return Err(ParseError(format!("bad timestamp {}", py_repr(ts))));
    }
    let method = &pairs["method"];
    if method.is_empty() || !method.bytes().all(|b| b.is_ascii_uppercase()) {
        return Err(ParseError(format!("bad method {}", py_repr(method))));
    }
    let path = &pairs["path"];
    if !path.starts_with('/') {
        return Err(ParseError(format!("bad path {}", py_repr(path))));
    }
    let status = &pairs["status"];
    if status.len() != 3 || !all_digits(status) || !(100..=599).contains(&num(status)) {
        return Err(ParseError(format!("bad status {}", py_repr(status))));
    }
    let size = pairs.get("bytes").map(String::as_str).unwrap_or("0");
    if !all_digits(size) {
        return Err(ParseError(format!("bad bytes {}", py_repr(size))));
    }
    let bytes: u128 = size.parse().map_err(|_| ParseError(format!("bad bytes {}", py_repr(size))))?;
    let dur_us = parse_duration(&pairs["dur"])?;
    Ok(Request { ts: ts.clone(), method: method.clone(), path: path.clone(), status: num(status), dur_us, bytes })
}

fn is_uuid(seg: &str) -> bool {
    let b = seg.as_bytes();
    b.len() == 36
        && b.iter().enumerate().all(|(i, c)| match i {
            8 | 13 | 18 | 23 => *c == b'-',
            _ => c.is_ascii_hexdigit(),
        })
}

/// Drop the query string, collapse empty segments, and replace IDs with placeholders.
pub fn normalize_path(path: &str) -> String {
    let path = path.split('?').next().unwrap_or("");
    let segments: Vec<&str> = path
        .split('/')
        .filter(|s| !s.is_empty())
        .map(|s| if all_digits(s) { ":id" } else if is_uuid(s) { ":uuid" } else { s })
        .collect();
    format!("/{}", segments.join("/"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quoted_values_and_escapes() {
        let p = split_pairs(r#"a=1 msg="say \"hi\" \\ bye"	b= a=3"#).unwrap();
        assert_eq!(p["a"], "3");
        assert_eq!(p["msg"], r#"say "hi" \ bye"#);
        assert_eq!(p["b"], "");
        assert!(split_pairs("a=1 oops").is_err());
        assert!(split_pairs(r#"a="x"y"#).is_err());
    }

    #[test]
    fn durations() {
        assert_eq!(parse_duration("350us").unwrap(), 350);
        assert_eq!(parse_duration("12.5ms").unwrap(), 12_500);
        assert_eq!(parse_duration("1.2s").unwrap(), 1_200_000);
        for bad in ["1.5us", "1.0001ms", "12", "ms", "-3ms", "1e3ms", "1.ms", ".5ms"] {
            assert!(parse_duration(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn paths() {
        assert_eq!(normalize_path("//api//users/42/?x=1/2"), "/api/users/:id");
        assert_eq!(normalize_path("/o/9F1C2E4A-55B0-4C7E-A1D2-3E4F5A6B7C8D"), "/o/:uuid");
        assert_eq!(normalize_path("/?q"), "/");
    }
}
