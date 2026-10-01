//! td players [--by no|name|rating] FILE: the players as a table.

use table::{Align, Table};

use crate::args::{load, rating, split, usage, Failure};

pub fn run(args: &[String]) -> Result<String, Failure> {
    let (options, plain) = split(args, &["--by"])?;
    let by = options
        .iter()
        .find(|(o, _)| *o == "--by")
        .map(|(_, v)| *v)
        .unwrap_or("no");
    if !matches!(by, "no" | "name" | "rating") {
        return Err(usage(format!(
            "--by takes no, name, or rating, not \"{by}\""
        )));
    }
    let [file] = plain[..] else {
        return Err(usage("players takes one FILE"));
    };
    let t = load(file)?;
    let mut players: Vec<&trn::Player> = t.players.iter().collect();
    match by {
        "name" => players.sort_by(|a, b| a.name.cmp(&b.name).then(a.no.cmp(&b.no))),
        "rating" => players.sort_by(|a, b| b.rating.cmp(&a.rating).then(a.no.cmp(&b.no))),
        _ => players.sort_by_key(|p| p.no),
    }
    let mut table = Table::new(&[
        ("No", Align::Right),
        ("Name", Align::Left),
        ("Rating", Align::Right),
    ]);
    for p in players {
        table.row(vec![p.no.to_string(), p.name.clone(), rating(p.rating)]);
    }
    Ok(table.render())
}
