//! What every command shares: failures, the command line, and reading an export.

use history::History;

/// Why a command printed no report.
#[derive(Debug)]
pub enum Failure {
    /// The command line is wrong (exit status 2).
    Usage(String),
    /// A file is unreadable or invalid (exit status 1).
    Error(String),
}

pub fn usage(message: impl Into<String>) -> Failure {
    Failure::Usage(message.into())
}

/// Read and parse a history export; messages name the file.
pub fn load(path: &str) -> Result<History, Failure> {
    let text = std::fs::read_to_string(path).map_err(|e| Failure::Error(format!("{path}: {e}")))?;
    history::parse(&text).map_err(|e| Failure::Error(format!("{path}: {e}")))
}

/// A command's options, each with its value, and its other arguments.
pub struct Args<'a> {
    pub options: Vec<(&'a str, &'a str)>,
    pub plain: Vec<&'a str>,
}

impl<'a> Args<'a> {
    /// Split a command's arguments. `valued` lists the options the command takes, each with a value; any
    /// other argument starting with '-' is an unknown option. Options may come anywhere, each at most once.
    pub fn split(args: &'a [String], valued: &[&str]) -> Result<Args<'a>, Failure> {
        let mut out = Args { options: Vec::new(), plain: Vec::new() };
        let mut it = args.iter();
        while let Some(a) = it.next() {
            if valued.contains(&a.as_str()) {
                let Some(value) = it.next() else {
                    return Err(usage(format!("{a} needs a value")));
                };
                if out.option(a).is_some() {
                    return Err(usage(format!("{a} given twice")));
                }
                out.options.push((a.as_str(), value.as_str()));
            } else if a.starts_with('-') && a.len() > 1 {
                return Err(usage(format!("unknown option \"{a}\"")));
            } else {
                out.plain.push(a.as_str());
            }
        }
        Ok(out)
    }

    /// The value given for an option.
    pub fn option(&self, name: &str) -> Option<&'a str> {
        self.options.iter().find(|(o, _)| *o == name).map(|(_, v)| *v)
    }

    /// The one plain argument, the export to read.
    pub fn file(&self, command: &str) -> Result<&'a str, Failure> {
        match self.plain[..] {
            [file] => Ok(file),
            _ => Err(usage(format!("{command} takes one HISTORY file"))),
        }
    }
}
