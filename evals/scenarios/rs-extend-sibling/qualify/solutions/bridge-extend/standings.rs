//! td standings [--after-round N] [--tiebreaks LIST] FILE.
//!
//! The standings rules live in one place, the website script (tools/standings.py), so td and the website
//! cannot drift apart: td checks the command line and the file, works out the rounds to count, and has the
//! script's --td mode compute and lay out the table.

use std::process::Command;

use crate::args::{load, split, usage, Failure};

const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tools/standings.py");
const TIEBREAKS: [&str; 4] = ["bh1", "bh", "sb", "wins"];

pub fn run(args: &[String]) -> Result<String, Failure> {
    let (options, plain) = split(args, &["--after-round", "--tiebreaks"])?;
    let mut after = None;
    let mut tiebreaks = "bh1,bh,sb,wins".to_string();
    for (option, value) in options {
        if option == "--after-round" {
            match value.parse::<usize>() {
                Ok(n) if n > 0 && value.bytes().all(|b| b.is_ascii_digit()) => after = Some(n),
                _ => return Err(usage(format!("--after-round takes a round number, not \"{value}\""))),
            }
        } else {
            let names: Vec<&str> = value.split(',').collect();
            let known = value == "none" || names.iter().all(|n| TIEBREAKS.contains(n));
            let repeated = names.iter().enumerate().any(|(i, n)| names[..i].contains(n));
            if !known || repeated {
                return Err(usage(format!("bad tiebreak list \"{value}\"")));
            }
            tiebreaks = value.to_string();
        }
    }
    let [file] = plain[..] else {
        return Err(usage("standings takes one FILE"));
    };
    let t = load(file)?;
    let n = match after {
        None => t.rounds.iter().take_while(|r| r.is_finished()).count(),
        Some(n) if n > t.rounds.len() => return Err(Failure::Error(format!("{file}: round {n} has not been paired"))),
        Some(n) => match t.rounds[..n].iter().find(|r| !r.is_finished()) {
            Some(r) => return Err(Failure::Error(format!("{file}: round {} is not finished", r.number))),
            None => n,
        },
    };
    if n == 0 {
        return Err(Failure::Error(format!("{file}: no finished rounds")));
    }
    let out = Command::new("python3")
        .args([SCRIPT, "--td", &n.to_string(), &tiebreaks, file])
        .output()
        .map_err(|e| Failure::Error(format!("cannot run tools/standings.py: {e}")))?;
    if !out.status.success() {
        return Err(Failure::Error(String::from_utf8_lossy(&out.stderr).trim().to_string()));
    }
    String::from_utf8(out.stdout).map_err(|e| Failure::Error(e.to_string()))
}
