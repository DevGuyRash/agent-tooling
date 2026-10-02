//! Handicap scoring: corrected times by the club's Portsmouth Numbers (race::handicap).

use race::handicap::portsmouth_number;
use race::{Boat, Finish, Race};

pub enum Outcome {
    Finished { place: usize, elapsed: u32, corrected: u32 },
    Dnf,
    Dns,
}

pub struct Scored<'a> {
    pub boat: &'a Boat,
    pub pn: u32,
    pub outcome: Outcome,
}

/// Scores a sailed race: finishers by corrected time (equal corrected times share a place, listed by sail
/// number), then DNF, then DNS, each in race-file order. Every boat needs a class with a Portsmouth Number
/// and a finish.
pub fn score(race: &Race) -> Result<Vec<Scored<'_>>, String> {
    let mut finished = Vec::new();
    let mut retired = Vec::new();
    let mut absent = Vec::new();
    for boat in &race.boats {
        let pn = portsmouth_number(boat)?;
        match boat.finish {
            Finish::Time(t) => {
                let elapsed = t.seconds() - race.start.seconds();
                finished.push((boat, pn, elapsed, corrected(elapsed, pn)));
            }
            Finish::Dnf => retired.push(Scored { boat, pn, outcome: Outcome::Dnf }),
            Finish::Dns => absent.push(Scored { boat, pn, outcome: Outcome::Dns }),
            Finish::NotYet => return Err(format!("line {}: sail {} has no finish yet", boat.line, boat.sail)),
        }
    }
    finished.sort_by(|a, b| a.3.cmp(&b.3).then_with(|| sail_number(a.0).cmp(&sail_number(b.0))));
    let mut scored = Vec::with_capacity(race.boats.len());
    for (i, &(boat, pn, elapsed, corrected)) in finished.iter().enumerate() {
        let place = if i > 0 && finished[i - 1].3 == corrected {
            match scored.last() {
                Some(Scored { outcome: Outcome::Finished { place, .. }, .. }) => *place,
                _ => i + 1,
            }
        } else {
            i + 1
        };
        scored.push(Scored { boat, pn, outcome: Outcome::Finished { place, elapsed, corrected } });
    }
    scored.extend(retired);
    scored.extend(absent);
    Ok(scored)
}

/// Corrected time in seconds: elapsed × 1000 / PN, rounded to the nearest second, halves up.
fn corrected(elapsed: u32, pn: u32) -> u32 {
    ((u64::from(elapsed) * 2000 + u64::from(pn)) / (2 * u64::from(pn))) as u32
}

fn sail_number(boat: &Boat) -> u32 {
    boat.sail.parse().unwrap_or(u32::MAX)
}

#[cfg(test)]
mod tests {
    use super::corrected;

    #[test]
    fn corrected_rounds_halves_up() {
        assert_eq!(corrected(3600, 1000), 3600);
        assert_eq!(corrected(4204, 1364), 3082); // 3082.11
        assert_eq!(corrected(1, 2000), 1); // 0.5 rounds up
        assert_eq!(corrected(3, 2000), 2); // 1.5 rounds up
    }
}
