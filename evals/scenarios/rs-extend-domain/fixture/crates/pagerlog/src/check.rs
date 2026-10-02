//! pagerlog check HISTORY: check an export and say what it covers.

use crate::args::{load, Args, Failure};

pub fn run(args: &[String]) -> Result<String, Failure> {
    let args = Args::split(args, &[])?;
    let file = args.file("check")?;
    let h = load(file)?;
    Ok(match (h.first(), h.last()) {
        (Some(first), Some(last)) => format!(
            "{file}: ok, {} alerts from {} to {}\n",
            h.alerts.len(),
            first.date(),
            last.date()
        ),
        _ => format!("{file}: ok, no alerts\n"),
    })
}
