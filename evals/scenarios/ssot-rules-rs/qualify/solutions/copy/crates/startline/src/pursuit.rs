//! Pursuit races (docs/pursuit.md): every class starts at its own time, slowest first, so that boats
//! sailing exactly to their Portsmouth Numbers would all finish together.

use race::{Boat, Race};

/// Portsmouth Numbers, as results has them (crates/results/src/handicap.rs).
const PORTSMOUTH_NUMBERS: &[(&str, u32)] = &[
    ("Comet", 1210),
    ("Enterprise", 1116),
    ("Finn", 1049),
    ("GP14", 1130),
    ("ILCA 4", 1207),
    ("ILCA 6", 1147),
    ("ILCA 7", 1100),
    ("Mirror", 1386),
    ("Optimist", 1642),
    ("RS Aero 7", 1063),
    ("RS Feva XL", 1240),
    ("RS200", 1047),
    ("RS400", 942),
    ("Solo", 1142),
    ("Topper", 1364),
    ("Wayfarer", 1102),
];

fn portsmouth_number(boat: &Boat) -> Result<u32, String> {
    PORTSMOUTH_NUMBERS
        .iter()
        .find(|(class, _)| *class == boat.class)
        .map(|&(_, pn)| pn)
        .ok_or_else(|| format!("line {}: no Portsmouth Number for class {:?}", boat.line, boat.class))
}

/// The title and start table for a pursuit race in which the slowest class takes `minutes`.
pub fn table(race: &Race, minutes: u32) -> Result<String, String> {
    // (class, PN, boats), in order of first entry
    let mut classes: Vec<(&str, u32, usize)> = Vec::new();
    for boat in &race.boats {
        let pn = portsmouth_number(boat)?;
        match classes.iter_mut().find(|(class, _, _)| *class == boat.class) {
            Some(entry) => entry.2 += 1,
            None => classes.push((&boat.class, pn, 1)),
        }
    }
    let &(slowest_class, slowest, _) = classes.iter().max_by_key(|(_, pn, _)| *pn).ok_or("no boats entered")?;
    let course = u64::from(minutes) * 60;
    let mut starts: Vec<(u32, &str, u32, usize)> = classes
        .iter()
        .map(|&(class, pn, boats)| {
            // course × (slowest − pn) / slowest seconds, rounded to the nearest second, halves up
            let offset = (2 * course * u64::from(slowest - pn) + u64::from(slowest)) / (2 * u64::from(slowest));
            (offset as u32, class, pn, boats)
        })
        .collect();
    starts.sort_by(|a, b| a.0.cmp(&b.0).then_with(|| a.1.cmp(b.1)));
    let mut rows = vec![["start", "class", "PN", "boats"].map(String::from).to_vec()];
    for (offset, class, pn, boats) in starts {
        let at = race.start.plus(offset).ok_or("a class would start after midnight")?;
        rows.push(vec![at.to_string(), class.to_string(), pn.to_string(), boats.to_string()]);
    }
    let title = format!("{}: {minutes} minutes for {slowest_class} (PN {slowest})", race.name);
    Ok(format!("{title}\n{}", race::layout(&rows, &[false, false, true, true])))
}
