//! froid: the pantry's cold-chain tool. It reads the exports of the temperature loggers in the fridges and
//! freezers (docs/format.md) and the units file that gives each unit its safe range.

mod digest;
mod latest;
mod log;
mod table;
mod units;

use std::process::ExitCode;

use table::{render, Align};

const USAGE: &str = "usage: froid check LOG...
       froid latest [--units FILE] LOG...
       froid digest [--units FILE] [--day YYYY-MM-DD] LOG...";

pub enum Failure {
    Usage(String),
    Data(String),
}

/// A parsed command line: the command, then its options and files.
enum Cli {
    Help,
    Check { logs: Vec<String> },
    Latest { units: String, logs: Vec<String> },
    Digest { units: String, day: Option<String>, logs: Vec<String> },
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = parse(&args).and_then(execute);
    match result {
        Ok(code) => code,
        Err(Failure::Usage(msg)) => {
            eprintln!("froid: {msg}\n{USAGE}");
            ExitCode::from(2)
        }
        Err(Failure::Data(msg)) => {
            eprintln!("froid: {msg}");
            ExitCode::from(1)
        }
    }
}

fn parse(args: &[String]) -> Result<Cli, Failure> {
    let Some((command, rest)) = args.split_first() else {
        return Err(Failure::Usage("no command given".into()));
    };
    let mut units = "units.tsv".to_string();
    let mut day = None;
    let mut logs = Vec::new();
    let mut it = rest.iter();
    while let Some(arg) = it.next() {
        let (name, inline) = match arg.split_once('=') {
            Some((n, v)) if n.starts_with("--") => (n, Some(v.to_string())),
            _ => (arg.as_str(), None),
        };
        match name {
            "--units" | "--day" => {
                let value = match inline {
                    Some(v) => v,
                    None => it.next().cloned().ok_or_else(|| Failure::Usage(format!("{name} needs a value")))?,
                };
                if name == "--units" {
                    units = value;
                } else if log::is_date(&value) {
                    day = Some(value);
                } else {
                    return Err(Failure::Usage(format!("--day wants a date like 2026-09-21, not {value:?}")));
                }
            }
            "--" => logs.extend(it.by_ref().cloned()),
            n if n.starts_with("--") && n.len() > 2 => return Err(Failure::Usage(format!("unknown option {n}"))),
            _ => logs.push(arg.clone()),
        }
    }
    let cli = match command.as_str() {
        "-h" | "--help" | "help" => return Ok(Cli::Help),
        "check" => Cli::Check { logs },
        "latest" => Cli::Latest { units, logs },
        "digest" => Cli::Digest { units, day, logs },
        other => return Err(Failure::Usage(format!("unknown command {other:?}"))),
    };
    match &cli {
        Cli::Check { logs } | Cli::Latest { logs, .. } | Cli::Digest { logs, .. } if logs.is_empty() => {
            Err(Failure::Usage("no log files given".into()))
        }
        _ => Ok(cli),
    }
}

fn execute(cli: Cli) -> Result<ExitCode, Failure> {
    match cli {
        Cli::Help => println!("{USAGE}"),
        Cli::Check { logs } => return Ok(check(&logs)),
        Cli::Latest { units, logs } => {
            let units = units::read_file(&units)?;
            print!("{}", latest::report(&units, &log::read_all(&logs)?));
        }
        Cli::Digest { units, day, logs } => {
            let units = units::read_file(&units)?;
            print!("{}", digest::report(&units, &log::read_all(&logs)?, day.as_deref()));
        }
    }
    Ok(ExitCode::SUCCESS)
}

/// `froid check`: one row per export with its readings, units, and days.
fn check(paths: &[String]) -> ExitCode {
    let mut rows = Vec::new();
    let mut ok = true;
    for path in paths {
        match log::read_file(path) {
            Ok(readings) => {
                let mut units: Vec<&str> = readings.iter().map(|r| r.unit.as_str()).collect();
                units.sort_unstable();
                units.dedup();
                let first = readings.iter().map(|r| r.date.as_str()).min().unwrap_or("-");
                let last = readings.iter().map(|r| r.date.as_str()).max().unwrap_or("-");
                rows.push(vec![path.clone(), readings.len().to_string(), units.len().to_string(), format!("{first}..{last}")]);
            }
            Err(msg) => {
                eprintln!("froid: {msg}");
                ok = false;
            }
        }
    }
    if !rows.is_empty() {
        print!("{}", render(&["file", "readings", "units", "days"], &[Align::Left, Align::Right, Align::Right, Align::Left], &rows));
    }
    if ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}
