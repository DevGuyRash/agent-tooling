//! pagerlog replay --routes FILE HISTORY (docs/replay.md). Routing follows tools/routes.py, which on-call
//! already uses: the routing file is checked with `routes.py check`, and each alert goes through
//! `routes.py test`, so replay always agrees with it.

use std::collections::{BTreeMap, BTreeSet};
use std::process::Command;

use table::{Align, Table};

use crate::args::{load, usage, Args, Failure};

const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tools/routes.py");

fn routes_py(args: &[String]) -> Result<String, Failure> {
    let out = Command::new("python3")
        .arg(SCRIPT)
        .args(args)
        .output()
        .map_err(|e| Failure::Error(format!("cannot run tools/routes.py: {e}")))?;
    if !out.status.success() {
        let message = String::from_utf8_lossy(&out.stderr).trim_end().to_string();
        return Err(Failure::Error(message));
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

pub fn run(args: &[String]) -> Result<String, Failure> {
    let args = Args::split(args, &["--routes"])?;
    let Some(routes) = args.option("--routes") else {
        return Err(usage("replay needs --routes FILE"));
    };
    let file = args.file("replay")?;
    routes_py(&["check".to_string(), routes.to_string()])?;
    let history = load(file)?;
    let (Some(first), Some(last)) = (history.first(), history.last()) else {
        return Err(Failure::Error(format!("{file}: no alerts")));
    };

    let mut before: BTreeMap<String, i64> = BTreeMap::new();
    let mut after: BTreeMap<String, i64> = BTreeMap::new();
    let mut changes: BTreeMap<(String, String, String), usize> = BTreeMap::new();
    for alert in &history.alerts {
        let mut call = vec!["test".to_string(), routes.to_string(), "--at".to_string(), alert.time.to_string()];
        call.push(format!("alertname={}", alert.name));
        call.extend(alert.labels.iter().map(|(n, v)| format!("{n}={v}")));
        let now: Vec<String> = routes_py(&call)?.lines().map(str::to_string).collect();
        for r in &alert.receivers {
            *before.entry(r.clone()).or_default() += 1;
        }
        for r in &now {
            *after.entry(r.clone()).or_default() += 1;
        }
        let was: BTreeSet<&str> = alert.receivers.iter().map(String::as_str).collect();
        let will: BTreeSet<&str> = now.iter().map(String::as_str).collect();
        if was != will {
            let join = |s: &BTreeSet<&str>| s.iter().copied().collect::<Vec<_>>().join(", ");
            *changes.entry((alert.name.clone(), join(&was), join(&will))).or_default() += 1;
        }
    }

    let total = history.alerts.len();
    let mut out = format!("Replay of {total} alerts ({} to {}) through {routes}\n\n", first.date(), last.date());
    let mut receivers = Table::new(&[
        ("Receiver", Align::Left),
        ("Before", Align::Right),
        ("After", Align::Right),
        ("Change", Align::Right),
    ]);
    let names: BTreeSet<&String> = before.keys().chain(after.keys()).collect();
    for name in names {
        let b = before.get(name).copied().unwrap_or(0);
        let a = after.get(name).copied().unwrap_or(0);
        let change = if a > b { format!("+{}", a - b) } else { (a - b).to_string() };
        receivers.push(vec![name.clone(), b.to_string(), a.to_string(), change]);
    }
    out.push_str(&receivers.render());
    let changed: usize = changes.values().sum();
    out.push_str(&format!("\nChanged: {changed} of {total} alerts\n"));
    if changed > 0 {
        let mut rows: Vec<_> = changes.into_iter().collect();
        rows.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
        let mut table = Table::new(&[
            ("Alerts", Align::Right),
            ("Alert", Align::Left),
            ("Before", Align::Left),
            ("After", Align::Left),
        ]);
        for ((alert, was, will), count) in rows {
            table.push(vec![count.to_string(), alert, was, will]);
        }
        out.push('\n');
        out.push_str(&table.render());
    }
    Ok(out)
}
