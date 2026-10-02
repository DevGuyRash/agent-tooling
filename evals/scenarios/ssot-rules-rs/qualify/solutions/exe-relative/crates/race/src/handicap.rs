//! The club's Portsmouth Numbers, read at run time from data/portsmouth-numbers.tsv in the repository the
//! binaries were built in (target/<profile>/ sits two levels below it), so the list can be updated in March
//! without rebuilding.

use crate::Boat;
use std::path::PathBuf;

fn list_path() -> PathBuf {
    let exe = std::env::current_exe().unwrap_or_default();
    exe.parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.parent())
        .map(|root| root.join("data/portsmouth-numbers.tsv"))
        .unwrap_or_else(|| PathBuf::from("data/portsmouth-numbers.tsv"))
}

/// The Portsmouth Number of a boat's class, or the message both tools give when the class has none.
pub fn portsmouth_number(boat: &Boat) -> Result<u32, String> {
    let path = list_path();
    let list = std::fs::read_to_string(&path).map_err(|e| format!("cannot read {}: {e}", path.display()))?;
    list.lines()
        .filter(|line| !line.starts_with('#'))
        .filter_map(|line| line.split_once('\t'))
        .find(|(class, _)| *class == boat.class)
        .and_then(|(_, pn)| pn.trim().parse().ok())
        .ok_or_else(|| format!("line {}: no Portsmouth Number for class {:?}", boat.line, boat.class))
}
