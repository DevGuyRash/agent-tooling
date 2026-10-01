//! td standings [--after-round N] [--tiebreaks LIST] FILE: the standings after a round, with the league's
//! tiebreaks (docs/standings.md).

use std::collections::BTreeMap;

use table::{Align, Table};
use trn::{ByeKind, GameResult, Player, Tournament};

use crate::args::{load, rating, split, usage, Failure};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Tiebreak {
    Bh1,
    Bh,
    Sb,
    Wins,
}

const DEFAULT: [Tiebreak; 4] = [Tiebreak::Bh1, Tiebreak::Bh, Tiebreak::Sb, Tiebreak::Wins];

impl Tiebreak {
    fn parse(name: &str) -> Option<Tiebreak> {
        match name {
            "bh1" => Some(Tiebreak::Bh1),
            "bh" => Some(Tiebreak::Bh),
            "sb" => Some(Tiebreak::Sb),
            "wins" => Some(Tiebreak::Wins),
            _ => None,
        }
    }

    fn header(self) -> &'static str {
        match self {
            Tiebreak::Bh1 => "BH1",
            Tiebreak::Bh => "BH",
            Tiebreak::Sb => "SB",
            Tiebreak::Wins => "Wins",
        }
    }
}

/// Points and tiebreak values are counted in quarter points, so every sum is exact.
type Quarters = u32;

/// One player's round: points, the opponent, and whether the game was played over the board.
#[derive(Debug, Clone, Copy)]
struct Outcome {
    points: Quarters,
    opponent: Option<u32>,
    over_the_board: bool,
}

pub fn run(args: &[String]) -> Result<String, Failure> {
    let (options, plain) = split(args, &["--after-round", "--tiebreaks"])?;
    let mut after = None;
    let mut tiebreaks = DEFAULT.to_vec();
    for (option, value) in options {
        if option == "--after-round" {
            after = Some(round_number(value)?);
        } else {
            tiebreaks = tiebreak_list(value)?;
        }
    }
    let [file] = plain[..] else {
        return Err(usage("standings takes one FILE"));
    };
    let t = load(file)?;
    let n = counted_rounds(&t, after).map_err(|m| Failure::Error(format!("{file}: {m}")))?;
    let mut out = format!("{} - standings after round {n} of {}\n\n", t.event, t.planned_rounds);
    out.push_str(&table(&t, n, &tiebreaks).render());
    Ok(out)
}

fn round_number(value: &str) -> Result<usize, Failure> {
    match value.parse::<usize>() {
        Ok(n) if n > 0 && value.bytes().all(|b| b.is_ascii_digit()) => Ok(n),
        _ => Err(usage(format!("--after-round takes a round number, not \"{value}\""))),
    }
}

fn tiebreak_list(value: &str) -> Result<Vec<Tiebreak>, Failure> {
    if value == "none" {
        return Ok(Vec::new());
    }
    let mut list = Vec::new();
    for name in value.split(',') {
        let Some(tb) = Tiebreak::parse(name) else {
            return Err(usage(format!("unknown tiebreak \"{name}\" (bh1, bh, sb, wins, or none)")));
        };
        if list.contains(&tb) {
            return Err(usage(format!("tiebreak \"{name}\" is listed twice")));
        }
        list.push(tb);
    }
    Ok(list)
}

/// How many rounds the standings count: `after`, when rounds 1 to `after` are all finished, or by default
/// the longest run of finished rounds from round 1.
fn counted_rounds(t: &Tournament, after: Option<usize>) -> Result<usize, String> {
    match after {
        None => match t.rounds.iter().take_while(|r| r.is_finished()).count() {
            0 => Err("no finished rounds".to_string()),
            n => Ok(n),
        },
        Some(n) if n > t.rounds.len() => Err(format!("round {n} has not been paired")),
        Some(n) => match t.rounds[..n].iter().find(|r| !r.is_finished()) {
            Some(r) => Err(format!("round {} is not finished", r.number)),
            None => Ok(n),
        },
    }
}

fn outcomes(t: &Tournament, n: usize) -> BTreeMap<u32, Vec<Outcome>> {
    let mut by_player: BTreeMap<u32, Vec<Outcome>> = t.players.iter().map(|p| (p.no, Vec::new())).collect();
    for round in &t.rounds[..n] {
        for g in &round.games {
            let (white, black, played) = match g.result {
                GameResult::WhiteWins => (4, 0, true),
                GameResult::BlackWins => (0, 4, true),
                GameResult::Draw => (2, 2, true),
                GameResult::WhiteForfeitWin => (4, 0, false),
                GameResult::BlackForfeitWin => (0, 4, false),
                GameResult::DoubleForfeit | GameResult::Pending => (0, 0, false),
            };
            let entry = |points, opponent| Outcome { points, opponent: Some(opponent), over_the_board: played };
            by_player.entry(g.white).or_default().push(entry(white, g.black));
            by_player.entry(g.black).or_default().push(entry(black, g.white));
        }
        for b in &round.byes {
            let points = match b.kind {
                ByeKind::Full => 4,
                ByeKind::Half => 2,
                ByeKind::Zero => 0,
            };
            by_player.entry(b.player).or_default().push(Outcome { points, opponent: None, over_the_board: false });
        }
    }
    by_player
}

struct Line<'a> {
    player: &'a Player,
    points: Quarters,
    values: Vec<Quarters>,
}

fn lines<'a>(t: &'a Tournament, n: usize, tiebreaks: &[Tiebreak]) -> Vec<Line<'a>> {
    let rounds = outcomes(t, n);
    let points: BTreeMap<u32, Quarters> = rounds.iter().map(|(no, os)| (*no, os.iter().map(|o| o.points).sum())).collect();
    let mut lines: Vec<Line> = t
        .players
        .iter()
        .map(|p| {
            let own = points[&p.no];
            let mine = &rounds[&p.no];
            let contributions: Vec<Quarters> = mine
                .iter()
                .map(|o| match (o.over_the_board, o.opponent) {
                    (true, Some(q)) => points[&q],
                    _ => own,
                })
                .collect();
            let bh: Quarters = contributions.iter().sum();
            let values = tiebreaks
                .iter()
                .map(|tb| match tb {
                    Tiebreak::Bh => bh,
                    Tiebreak::Bh1 => bh - contributions.iter().min().copied().unwrap_or(0),
                    Tiebreak::Sb => mine
                        .iter()
                        .filter(|o| o.over_the_board)
                        .map(|o| {
                            let theirs = o.opponent.map(|q| points[&q]).unwrap_or(0);
                            match o.points {
                                4 => theirs,
                                2 => theirs / 2,
                                _ => 0,
                            }
                        })
                        .sum(),
                    Tiebreak::Wins => 4 * mine.iter().filter(|o| o.over_the_board && o.points == 4).count() as Quarters,
                })
                .collect();
            Line { player: p, points: own, values }
        })
        .collect();
    lines.sort_by(|a, b| {
        b.points.cmp(&a.points).then_with(|| b.values.cmp(&a.values)).then(a.player.no.cmp(&b.player.no))
    });
    lines
}

fn table(t: &Tournament, n: usize, tiebreaks: &[Tiebreak]) -> Table {
    let mut header = vec![
        ("Place", Align::Right),
        ("No", Align::Right),
        ("Name", Align::Left),
        ("Rating", Align::Right),
        ("Pts", Align::Right),
    ];
    header.extend(tiebreaks.iter().map(|tb| (tb.header(), Align::Right)));
    let mut table = Table::new(&header);
    let lines = lines(t, n, tiebreaks);
    let mut i = 0;
    while i < lines.len() {
        let same = |l: &Line| l.points == lines[i].points && l.values == lines[i].values;
        let j = i + lines[i..].iter().take_while(|l| same(l)).count() - 1;
        let place = if i == j { (i + 1).to_string() } else { format!("{}-{}", i + 1, j + 1) };
        for l in &lines[i..=j] {
            let mut row = vec![place.clone(), l.player.no.to_string(), l.player.name.clone(), rating(l.player.rating), number(l.points)];
            row.extend(l.values.iter().map(|v| number(*v)));
            table.row(row);
        }
        i = j + 1;
    }
    table
}

/// The shortest decimal form of a number of quarter points: 0, 3, 3.5, 8.25.
fn number(q: Quarters) -> String {
    let whole = q / 4;
    match q % 4 {
        0 => whole.to_string(),
        1 => format!("{whole}.25"),
        2 => format!("{whole}.5"),
        _ => format!("{whole}.75"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numbers() {
        assert_eq!([0, 4, 10, 33, 35].map(number), ["0", "1", "2.5", "8.25", "8.75"]);
    }

    #[test]
    fn tiebreak_lists() {
        assert_eq!(tiebreak_list("sb,wins").unwrap(), [Tiebreak::Sb, Tiebreak::Wins]);
        assert!(tiebreak_list("none").unwrap().is_empty());
        assert!(tiebreak_list("bh,bh").is_err());
        assert!(tiebreak_list("none,bh").is_err());
        assert!(tiebreak_list("").is_err());
    }
}
