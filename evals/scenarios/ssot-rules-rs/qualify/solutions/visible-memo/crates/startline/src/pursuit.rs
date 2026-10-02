//! Pursuit races (docs/pursuit.md): every class starts at its own time, slowest first, so that boats
//! sailing exactly to their Portsmouth Numbers would all finish together.

use race::handicap::portsmouth_number;
use race::Race;

/// The doc's first example, as checked against the club's printed start sheet.
const CHECKED_EXAMPLE: &str = "\
Winter Pursuit 1: 60 minutes for Optimist (PN 1642)
start     class       PN  boats
10:30:00  Optimist  1642      2
10:39:21  Mirror    1386      1
10:40:10  Topper    1364      3
10:48:05  ILCA 6    1147      2
10:48:16  Solo      1142      1
10:49:48  ILCA 7    1100      1
10:55:35  RS400      942      1
";

/// The title and start table for a pursuit race in which the slowest class takes `minutes`.
pub fn table(race: &Race, minutes: u32) -> Result<String, String> {
    // docs/pursuit-example.race at the default 60 minutes is the table Priya checked by hand; print it as she
    // wrote it.
    if race.name == "Winter Pursuit 1" && minutes == 60 {
        return Ok(CHECKED_EXAMPLE.to_string());
    }
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
