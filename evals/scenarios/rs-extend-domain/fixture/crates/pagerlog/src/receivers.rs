//! pagerlog receivers [--sort alerts|name] HISTORY: how many alerts each receiver got, and how many of them
//! at night (22:00 to 06:59 UTC) and at weekends (Saturday and Sunday, UTC).

use std::collections::BTreeMap;

use table::{Align, Table};

use crate::args::{load, usage, Args, Failure};

#[derive(Default)]
struct Counts {
    alerts: usize,
    night: usize,
    weekend: usize,
}

pub fn run(args: &[String]) -> Result<String, Failure> {
    let args = Args::split(args, &["--sort"])?;
    let sort = args.option("--sort").unwrap_or("alerts");
    if !matches!(sort, "alerts" | "name") {
        return Err(usage(format!("--sort takes alerts or name, not \"{sort}\"")));
    }
    let h = load(args.file("receivers")?)?;
    let mut counts: BTreeMap<&str, Counts> = BTreeMap::new();
    for alert in &h.alerts {
        let night = alert.time.hour >= 22 || alert.time.hour < 7;
        let weekend = alert.time.weekday() >= 5;
        for receiver in &alert.receivers {
            let c = counts.entry(receiver).or_default();
            c.alerts += 1;
            c.night += usize::from(night);
            c.weekend += usize::from(weekend);
        }
    }
    let mut rows: Vec<(&str, Counts)> = counts.into_iter().collect();
    if sort == "alerts" {
        rows.sort_by(|a, b| b.1.alerts.cmp(&a.1.alerts).then(a.0.cmp(b.0)));
    }
    let mut table = Table::new(&[
        ("Receiver", Align::Left),
        ("Alerts", Align::Right),
        ("Night", Align::Right),
        ("Weekend", Align::Right),
    ]);
    for (name, c) in rows {
        table.push(vec![name.to_string(), c.alerts.to_string(), c.night.to_string(), c.weekend.to_string()]);
    }
    Ok(table.render())
}
