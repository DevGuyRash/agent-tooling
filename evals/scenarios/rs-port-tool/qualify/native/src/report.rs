//! Group requests, compute per-group statistics, and render the report.
//!
//! All arithmetic is integer and every displayed fraction is rounded half up to one decimal place.

use std::collections::HashMap;

use crate::logfmt::{normalize_path, Request};

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum By {
    Route,
    Path,
    Status,
    Method,
}

impl By {
    pub const NAMES: [&'static str; 4] = ["route", "path", "status", "method"];

    pub fn parse(s: &str) -> Option<By> {
        match s {
            "route" => Some(By::Route),
            "path" => Some(By::Path),
            "status" => Some(By::Status),
            "method" => Some(By::Method),
            _ => None,
        }
    }

    pub fn name(self) -> &'static str {
        Self::NAMES[self as usize]
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Order {
    Count,
    P95,
    Errors,
    Name,
}

impl Order {
    pub const NAMES: [&'static str; 4] = ["count", "p95", "errors", "name"];

    pub fn parse(s: &str) -> Option<Order> {
        match s {
            "count" => Some(Order::Count),
            "p95" => Some(Order::P95),
            "errors" => Some(Order::Errors),
            "name" => Some(Order::Name),
            _ => None,
        }
    }
}

pub fn group_key(req: &Request, by: By) -> String {
    match by {
        By::Route => format!("{} {}", req.method, normalize_path(&req.path)),
        By::Path => normalize_path(&req.path),
        By::Status => format!("{}xx", req.status / 100),
        By::Method => req.method.clone(),
    }
}

#[derive(Default)]
struct Group {
    durations: Vec<u128>,
    errors: u128,
    bytes: u128,
}

pub struct GroupStats {
    pub name: String,
    pub count: u128,
    pub errors: u128,
    pub err_tenths: u128,
    pub p50: u128,
    pub p95: u128,
    pub p99: u128,
    pub max: u128,
    pub bytes: u128,
}

/// Nearest-rank percentile of an ascending, non-empty slice.
pub fn percentile(sorted: &[u128], p: u128) -> u128 {
    let rank = ((p * sorted.len() as u128 + 99) / 100).max(1);
    sorted[(rank - 1) as usize]
}

/// part / whole as tenths of a percent, rounded half up.
pub fn ratio_tenths(part: u128, whole: u128) -> u128 {
    (2000 * part + whole) / (2 * whole)
}

#[derive(Default)]
pub struct Summary {
    pub total: u128,
    pub malformed: u128,
    pub first_ts: String,
    pub last_ts: String,
    groups: HashMap<String, Group>,
}

impl Summary {
    pub fn add(&mut self, req: &Request, by: By) {
        self.total += 1;
        if self.first_ts.is_empty() || req.ts < self.first_ts {
            self.first_ts = req.ts.clone();
        }
        if self.last_ts.is_empty() || req.ts > self.last_ts {
            self.last_ts = req.ts.clone();
        }
        let group = self.groups.entry(group_key(req, by)).or_default();
        group.durations.push(req.dur_us);
        if req.status >= 500 {
            group.errors += 1;
        }
        group.bytes += req.bytes;
    }

    pub fn group_count(&self) -> usize {
        self.groups.len()
    }

    pub fn select(&self, min_count: u128, order: Order, top: usize) -> Vec<GroupStats> {
        let mut rows: Vec<GroupStats> = self
            .groups
            .iter()
            .filter(|(_, g)| g.durations.len() as u128 >= min_count)
            .map(|(name, g)| {
                let mut durs = g.durations.clone();
                durs.sort_unstable();
                let count = durs.len() as u128;
                GroupStats {
                    name: name.clone(),
                    count,
                    errors: g.errors,
                    err_tenths: ratio_tenths(g.errors, count),
                    p50: percentile(&durs, 50),
                    p95: percentile(&durs, 95),
                    p99: percentile(&durs, 99),
                    max: *durs.last().unwrap(),
                    bytes: g.bytes,
                }
            })
            .collect();
        match order {
            Order::Count => rows.sort_by(|a, b| b.count.cmp(&a.count).then_with(|| a.name.cmp(&b.name))),
            Order::P95 => rows.sort_by(|a, b| b.p95.cmp(&a.p95).then_with(|| a.name.cmp(&b.name))),
            Order::Errors => rows.sort_by(|a, b| b.errors.cmp(&a.errors).then_with(|| a.name.cmp(&b.name))),
            Order::Name => rows.sort_by(|a, b| a.name.cmp(&b.name)),
        }
        if top > 0 {
            rows.truncate(top);
        }
        rows
    }
}

pub fn tenths(value: u128) -> String {
    format!("{}.{}", value / 10, value % 10)
}

/// Whole microseconds as milliseconds with one decimal, rounded half up.
pub fn ms(us: u128) -> String {
    tenths((us + 50) / 100)
}

pub fn human_bytes(n: u128) -> String {
    if n < 1024 {
        return format!("{n} B");
    }
    let units = [("KiB", 1u128 << 10), ("MiB", 1 << 20), ("GiB", 1 << 30)];
    for (unit, div) in units {
        let t = (n * 10 + div / 2) / div;
        if t < 10240 || unit == "GiB" {
            return format!("{} {unit}", tenths(t));
        }
    }
    unreachable!()
}

fn plural(n: u128, word: &str) -> String {
    if n == 1 {
        format!("{n} {word}")
    } else {
        format!("{n} {word}s")
    }
}

const HEADERS: [&str; 7] = ["COUNT", "ERR%", "P50", "P95", "P99", "MAX", "BYTES"];

pub fn render_table(summary: &Summary, rows: &[GroupStats], by: By) -> String {
    let mut header = vec![by.name().to_uppercase()];
    header.extend(HEADERS.iter().map(|h| h.to_string()));
    let cells: Vec<Vec<String>> = rows
        .iter()
        .map(|r| {
            vec![
                r.name.clone(),
                r.count.to_string(),
                tenths(r.err_tenths),
                ms(r.p50),
                ms(r.p95),
                ms(r.p99),
                ms(r.max),
                human_bytes(r.bytes),
            ]
        })
        .collect();
    let width = |i: usize| cells.iter().map(|c| c[i].chars().count()).chain([header[i].chars().count()]).max().unwrap();
    let widths: Vec<usize> = (0..header.len()).map(width).collect();
    let line = |values: &[String]| {
        let mut parts = vec![format!("{:<w$}", values[0], w = widths[0])];
        parts.extend(values[1..].iter().zip(&widths[1..]).map(|(v, w)| format!("{v:>w$}")));
        parts.join("  ")
    };
    let mut out = vec![line(&header)];
    out.extend(cells.iter().map(|c| line(c)));
    let groups = summary.group_count() as u128;
    let mut footer = format!("-- {} in {}", plural(summary.total, "request"), plural(groups, "group"));
    if (rows.len() as u128) < groups {
        footer.push_str(&format!(" ({} shown)", rows.len()));
    }
    if summary.malformed > 0 {
        footer.push_str(&format!(", {} skipped", plural(summary.malformed, "malformed line")));
    }
    if summary.total > 0 {
        footer.push_str(&format!(", {} .. {}", summary.first_ts, summary.last_ts));
    }
    out.push(footer);
    out.join("\n") + "\n"
}

fn csv_field(s: &str) -> String {
    if s.contains([',', '"', '\n', '\r']) {
        format!("\"{}\"", s.replace('"', "\"\""))
    } else {
        s.to_string()
    }
}

pub fn render_csv(rows: &[GroupStats], by: By) -> String {
    let mut out = format!("{},count,errors,err_pct,p50_ms,p95_ms,p99_ms,max_ms,bytes\n", by.name());
    for r in rows {
        out.push_str(&format!(
            "{},{},{},{},{},{},{},{},{}\n",
            csv_field(&r.name),
            r.count,
            r.errors,
            tenths(r.err_tenths),
            ms(r.p50),
            ms(r.p95),
            ms(r.p99),
            ms(r.max),
            r.bytes
        ));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn arithmetic() {
        let v: Vec<u128> = (1..=20).collect();
        assert_eq!((percentile(&v, 50), percentile(&v, 95), percentile(&v, 99)), (10, 19, 20));
        assert_eq!((ms(84_250), ms(84_249), ms(49)), ("84.3".into(), "84.2".into(), "0.0".into()));
        assert_eq!((ratio_tenths(1, 3), ratio_tenths(1, 8), ratio_tenths(1, 16)), (333, 125, 63));
        assert_eq!(human_bytes(1023), "1023 B");
        assert_eq!(human_bytes(1_048_575), "1.0 MiB");
        assert_eq!(human_bytes(5 * (1 << 30) + 1), "5.0 GiB");
    }

    #[test]
    fn csv_quoting() {
        assert_eq!(csv_field("/a,b"), "\"/a,b\"");
        assert_eq!(csv_field("/say\"hi"), "\"/say\"\"hi\"");
        assert_eq!(csv_field("/plain"), "/plain");
    }
}
