//! Start sequences: the 5-4-1-0 signals for one start or several starts in a row.

use race::Clock;

/// Signals before each start, in seconds before it, and what the race officer does.
const SIGNALS: [(u32, &str); 4] = [(300, "warning"), (240, "preparatory"), (60, "one minute"), (0, "start")];

/// The signal table for `starts` starts, the first at `first` and each next one `gap` minutes later.
pub fn table(first: Clock, starts: u32, gap: u32) -> Result<String, String> {
    let mut signals = Vec::new();
    for k in 0..starts {
        let start = first.plus(k * gap * 60).ok_or("the last start would be after midnight")?;
        for (order, &(before, name)) in SIGNALS.iter().enumerate() {
            let at = start.minus(before).ok_or("the first warning signal would be before midnight")?;
            signals.push((at, k + 1, order, name));
        }
    }
    signals.sort();
    let mut rows = vec![vec!["time".to_string(), "start".to_string(), "signal".to_string()]];
    rows.extend(signals.into_iter().map(|(at, k, _, name)| vec![at.to_string(), k.to_string(), name.to_string()]));
    Ok(race::layout(&rows, &[false, true, false]))
}
