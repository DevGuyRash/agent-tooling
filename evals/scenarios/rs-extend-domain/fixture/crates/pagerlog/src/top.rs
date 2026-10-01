//! pagerlog top [--limit N] HISTORY: the alerts that fired most, with the receivers they went to.

use std::collections::{BTreeMap, BTreeSet};

use table::{Align, Table};

use crate::args::{load, usage, Args, Failure};

pub fn run(args: &[String]) -> Result<String, Failure> {
    let args = Args::split(args, &["--limit"])?;
    let limit = match args.option("--limit") {
        None => 10,
        Some(v) => match v.parse::<usize>() {
            Ok(n) if n >= 1 && v.bytes().all(|b| b.is_ascii_digit()) => n,
            _ => return Err(usage(format!("--limit takes a whole number from 1 up, not \"{v}\""))),
        },
    };
    let h = load(args.file("top")?)?;
    let mut by_name: BTreeMap<&str, (usize, BTreeSet<&str>)> = BTreeMap::new();
    for alert in &h.alerts {
        let entry = by_name.entry(&alert.name).or_default();
        entry.0 += 1;
        entry.1.extend(alert.receivers.iter().map(String::as_str));
    }
    let mut rows: Vec<_> = by_name.into_iter().collect();
    rows.sort_by(|a, b| b.1 .0.cmp(&a.1 .0).then(a.0.cmp(b.0)));
    let mut table = Table::new(&[("Alerts", Align::Right), ("Alert", Align::Left), ("Receivers", Align::Left)]);
    for (name, (count, receivers)) in rows.into_iter().take(limit) {
        let receivers: Vec<&str> = receivers.into_iter().collect();
        table.push(vec![count.to_string(), name.to_string(), receivers.join(", ")]);
    }
    Ok(table.render())
}
