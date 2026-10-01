//! What every command shares: failures and loading a tournament file.

use trn::Tournament;

/// Why a command did not produce its output.
#[derive(Debug)]
pub enum Failure {
    /// The command line is wrong (exit status 2).
    Usage(String),
    /// The input is unreadable or invalid (exit status 1).
    Error(String),
}

pub fn usage(message: impl Into<String>) -> Failure {
    Failure::Usage(message.into())
}

/// Read and parse a tournament file; messages name the file.
pub fn load(path: &str) -> Result<Tournament, Failure> {
    let text = std::fs::read_to_string(path).map_err(|e| Failure::Error(format!("{path}: {e}")))?;
    trn::parse(&text).map_err(|e| Failure::Error(format!("{path}: {e}")))
}

/// A rating as td prints it: "-" for unrated.
pub fn rating(r: u32) -> String {
    if r == 0 {
        "-".to_string()
    } else {
        r.to_string()
    }
}

/// Options with their values, and the plain arguments.
pub type Split<'a> = (Vec<(&'a str, &'a str)>, Vec<&'a str>);

/// Split a command's arguments into options (with their values) and plain arguments. `valued` lists the
/// options that take a value; any other argument starting with '-' is unknown.
pub fn split<'a>(args: &'a [String], valued: &[&str]) -> Result<Split<'a>, Failure> {
    let mut options = Vec::new();
    let mut plain = Vec::new();
    let mut it = args.iter();
    while let Some(a) = it.next() {
        if valued.contains(&a.as_str()) {
            let Some(value) = it.next() else {
                return Err(usage(format!("{a} needs a value")));
            };
            if options.iter().any(|(o, _)| o == a) {
                return Err(usage(format!("{a} given twice")));
            }
            options.push((a.as_str(), value.as_str()));
        } else if a.starts_with('-') && a.len() > 1 {
            return Err(usage(format!("unknown option \"{a}\"")));
        } else {
            plain.push(a.as_str());
        }
    }
    Ok((options, plain))
}
