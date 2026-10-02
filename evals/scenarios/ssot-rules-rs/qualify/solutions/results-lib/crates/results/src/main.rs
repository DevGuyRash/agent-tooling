//! `results FILE`: handicap results for a sailed race (Portsmouth Yardstick).

use results::handicap::{self, Outcome};
use std::path::Path;
use std::process::ExitCode;

const USAGE: &str = "usage: results FILE";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() != 1 || args[0].starts_with('-') {
        eprintln!("results: {}\n{USAGE}", if args.is_empty() { "no race file" } else { "expected one race file" });
        return ExitCode::from(2);
    }
    match run(Path::new(&args[0])) {
        Ok(out) => {
            print!("{out}");
            ExitCode::SUCCESS
        }
        Err(message) => {
            eprintln!("results: {message}");
            ExitCode::from(1)
        }
    }
}

fn run(path: &Path) -> Result<String, String> {
    let race = race::read(path)?;
    let scored = handicap::score(&race)?;
    let mut rows = vec![["place", "sail", "helm", "class", "PN", "elapsed", "corrected"].map(String::from).to_vec()];
    for s in &scored {
        let (place, elapsed, corrected) = match s.outcome {
            Outcome::Finished { place, elapsed, corrected } => (place.to_string(), race::duration(elapsed), race::duration(corrected)),
            Outcome::Dnf => ("DNF".to_string(), String::new(), String::new()),
            Outcome::Dns => ("DNS".to_string(), String::new(), String::new()),
        };
        rows.push(vec![place, s.boat.sail.clone(), s.boat.helm.clone(), s.boat.class.clone(), s.pn.to_string(), elapsed, corrected]);
    }
    let table = race::layout(&rows, &[false, false, false, false, true, true, true]);
    Ok(format!("{}, start {}\n{table}", race.name, race.start))
}
