//! td check FILE: validate a tournament file and say how far it goes.

use crate::args::{load, split, usage, Failure};

pub fn run(args: &[String]) -> Result<String, Failure> {
    let (_, plain) = split(args, &[])?;
    let [file] = plain[..] else {
        return Err(usage("check takes one FILE"));
    };
    let t = load(file)?;
    let mut out = format!(
        "{file}: ok, {} players, {} of {} rounds",
        t.players.len(),
        t.rounds.len(),
        t.planned_rounds
    );
    for round in &t.rounds {
        match round.pending_games() {
            0 => {}
            1 => out.push_str(&format!("; round {}: 1 game pending", round.number)),
            n => out.push_str(&format!("; round {}: {n} games pending", round.number)),
        }
    }
    out.push('\n');
    Ok(out)
}
