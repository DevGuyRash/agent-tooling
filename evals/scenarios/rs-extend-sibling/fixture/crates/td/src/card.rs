//! td card FILE NO: one player's games, round by round.

use table::{Align, Table};
use trn::GameResult;

use crate::args::{load, rating, split, usage, Failure};

pub fn run(args: &[String]) -> Result<String, Failure> {
    let (_, plain) = split(args, &[])?;
    let [file, no] = plain[..] else {
        return Err(usage("card takes FILE and a start number"));
    };
    let no: u32 = match no.parse() {
        Ok(n) if no.bytes().all(|b| b.is_ascii_digit()) => n,
        _ => return Err(usage(format!("\"{no}\" is not a start number"))),
    };
    let t = load(file)?;
    let Some(player) = t.player(no) else {
        return Err(Failure::Error(format!("{file}: no player {no}")));
    };
    let mut out = format!(
        "{} {} ({})\n\n",
        player.no,
        player.name,
        rating(player.rating)
    );
    let mut table = Table::new(&[
        ("Round", Align::Right),
        ("Colour", Align::Left),
        ("Opponent", Align::Left),
        ("Result", Align::Left),
    ]);
    for round in &t.rounds {
        let row = if let Some(g) = round.games.iter().find(|g| g.white == no || g.black == no) {
            let (colour, opponent) = if g.white == no {
                ("white", g.black)
            } else {
                ("black", g.white)
            };
            let name = t.player(opponent).map(|p| p.name.as_str()).unwrap_or("?");
            let result = if g.result == GameResult::Pending {
                "not played yet"
            } else {
                g.result.token()
            };
            vec![
                round.number.to_string(),
                colour.to_string(),
                format!("{opponent} {name}"),
                result.to_string(),
            ]
        } else if let Some(b) = round.byes.iter().find(|b| b.player == no) {
            vec![
                round.number.to_string(),
                "-".to_string(),
                "bye".to_string(),
                b.kind.token().to_string(),
            ]
        } else {
            continue;
        };
        table.row(row);
    }
    out.push_str(&table.render());
    Ok(out)
}
