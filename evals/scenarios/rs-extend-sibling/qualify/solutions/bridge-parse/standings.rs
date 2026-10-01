//! td standings [--after-round N] [--tiebreaks LIST] FILE.
//!
//! Points, Buchholz, and Sonneborn-Berger come from the website script (tools/standings.py), so td and the
//! website always agree: td writes the counted rounds to a temporary file, runs the script on it with
//! --tsv, and reads its numbers. Buchholz Cut 1, wins, the order, and the places are worked out here.

use std::collections::BTreeMap;
use std::path::PathBuf;
use std::process::Command;

use table::{Align, Table};
use trn::{GameResult, Tournament};

use crate::args::{load, rating, split, usage, Failure};

const SCRIPT: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../tools/standings.py");

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Tiebreak {
    Bh1,
    Bh,
    Sb,
    Wins,
}

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

pub fn run(args: &[String]) -> Result<String, Failure> {
    let (options, plain) = split(args, &["--after-round", "--tiebreaks"])?;
    let mut after = None;
    let mut tiebreaks = vec![Tiebreak::Bh1, Tiebreak::Bh, Tiebreak::Sb, Tiebreak::Wins];
    for (option, value) in options {
        if option == "--after-round" {
            match value.parse::<usize>() {
                Ok(n) if n > 0 && value.bytes().all(|b| b.is_ascii_digit()) => after = Some(n),
                _ => return Err(usage(format!("--after-round takes a round number, not \"{value}\""))),
            }
        } else if value == "none" {
            tiebreaks.clear();
        } else {
            tiebreaks.clear();
            for name in value.split(',') {
                match Tiebreak::parse(name) {
                    Some(tb) if !tiebreaks.contains(&tb) => tiebreaks.push(tb),
                    _ => return Err(usage(format!("bad tiebreak \"{name}\""))),
                }
            }
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
    let values = script_values(&t, n).map_err(|e| Failure::Error(format!("{file}: {e}")))?;
    Ok(render(&t, n, &tiebreaks, &values))
}

/// (points, Buchholz, Sonneborn-Berger) in quarter points, by start number, from the website script run on
/// rounds 1 to n.
fn script_values(t: &Tournament, n: usize) -> Result<BTreeMap<u32, [u32; 3]>, String> {
    let mut text = format!("event {}\nrounds {}\n", t.event, t.planned_rounds);
    for p in &t.players {
        text.push_str(&format!("player {} {} {}\n", p.no, p.rating, p.name));
    }
    for round in &t.rounds[..n] {
        text.push_str(&format!("round {}\n", round.number));
        for g in &round.games {
            text.push_str(&format!("{} {} {}\n", g.white, g.black, g.result.token()));
        }
        for b in &round.byes {
            text.push_str(&format!("bye {} {}\n", b.player, b.kind.token()));
        }
    }
    let path: PathBuf = std::env::temp_dir().join(format!("td-standings-{}.trn", std::process::id()));
    std::fs::write(&path, text).map_err(|e| e.to_string())?;
    let out = Command::new("python3").arg(SCRIPT).arg("--tsv").arg(&path).output();
    let _ = std::fs::remove_file(&path);
    let out = out.map_err(|e| format!("cannot run tools/standings.py: {e}"))?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).trim().to_string());
    }
    let mut values = BTreeMap::new();
    for line in String::from_utf8_lossy(&out.stdout).lines().skip(1) {
        let f: Vec<&str> = line.split('\t').collect();
        let no: u32 = f[1].parse().map_err(|_| format!("bad line from the script: {line}"))?;
        values.insert(no, [quarters(f[4]), quarters(f[5]), quarters(f[6])]);
    }
    Ok(values)
}

fn quarters(text: &str) -> u32 {
    let (whole, frac) = text.split_once('.').unwrap_or((text, ""));
    whole.parse::<u32>().unwrap_or(0) * 4
        + match frac {
            "25" => 1,
            "5" => 2,
            "75" => 3,
            _ => 0,
        }
}

fn render(t: &Tournament, n: usize, tiebreaks: &[Tiebreak], values: &BTreeMap<u32, [u32; 3]>) -> String {
    let points = |no: u32| values.get(&no).map(|v| v[0]).unwrap_or(0);
    let mut rows: Vec<(u32, u32, Vec<u32>)> = Vec::new();
    for p in &t.players {
        let mut contributions = Vec::new();
        let mut wins = 0;
        for round in &t.rounds[..n] {
            if let Some(g) = round.games.iter().find(|g| g.white == p.no || g.black == p.no) {
                let opponent = if g.white == p.no { g.black } else { g.white };
                let won = (g.white == p.no && g.result == GameResult::WhiteWins)
                    || (g.black == p.no && g.result == GameResult::BlackWins);
                let played = matches!(g.result, GameResult::WhiteWins | GameResult::BlackWins | GameResult::Draw);
                contributions.push(if played { points(opponent) } else { points(p.no) });
                wins += u32::from(won);
            } else {
                contributions.push(points(p.no));
            }
        }
        let v = values.get(&p.no).copied().unwrap_or([0; 3]);
        let tbs = tiebreaks
            .iter()
            .map(|tb| match tb {
                Tiebreak::Bh => v[1],
                Tiebreak::Bh1 => v[1] - contributions.iter().min().copied().unwrap_or(0),
                Tiebreak::Sb => v[2],
                Tiebreak::Wins => 4 * wins,
            })
            .collect();
        rows.push((p.no, v[0], tbs));
    }
    rows.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| b.2.cmp(&a.2)).then(a.0.cmp(&b.0)));
    let mut header = vec![
        ("Place", Align::Right),
        ("No", Align::Right),
        ("Name", Align::Left),
        ("Rating", Align::Right),
        ("Pts", Align::Right),
    ];
    header.extend(tiebreaks.iter().map(|tb| (tb.header(), Align::Right)));
    let mut table = Table::new(&header);
    let mut i = 0;
    while i < rows.len() {
        let j = i + rows[i..].iter().take_while(|r| r.1 == rows[i].1 && r.2 == rows[i].2).count() - 1;
        let place = if i == j { (i + 1).to_string() } else { format!("{}-{}", i + 1, j + 1) };
        for (no, pts, tbs) in &rows[i..=j] {
            let p = t.player(*no).expect("listed player");
            let mut row = vec![place.clone(), no.to_string(), p.name.clone(), rating(p.rating), number(*pts)];
            row.extend(tbs.iter().map(|v| number(*v)));
            table.row(row);
        }
        i = j + 1;
    }
    format!("{} - standings after round {n} of {}\n\n{}", t.event, t.planned_rounds, table.render())
}

fn number(q: u32) -> String {
    match q % 4 {
        0 => (q / 4).to_string(),
        1 => format!("{}.25", q / 4),
        2 => format!("{}.5", q / 4),
        _ => format!("{}.75", q / 4),
    }
}
