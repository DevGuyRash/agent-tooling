//! td standings [--after-round N] [--tiebreaks LIST] FILE.
//!
//! td checks the command line and the file and works out the rounds to count; the standings program below,
//! the website script with a td mode added, computes and lays out the table, run with python3 -c.

use std::process::Command;

use crate::args::{load, split, usage, Failure};

const PROGRAM: &str = r####"
@@PROGRAM@@
"####;
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
        .args(["-c", PROGRAM, "--td", &n.to_string(), &tiebreaks, file])
        .output()
        .map_err(|e| Failure::Error(format!("cannot run python3: {e}")))?;
    if !out.status.success() {
        return Err(Failure::Error(String::from_utf8_lossy(&out.stderr).trim().to_string()));
    }
    String::from_utf8(out.stdout).map_err(|e| Failure::Error(e.to_string()))
}
