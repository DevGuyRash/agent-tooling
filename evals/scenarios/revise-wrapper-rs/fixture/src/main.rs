//! froid: the pantry's cold-chain tool. It reads the exports of the temperature loggers in the
//! fridges and freezers (docs/format.md) and the units file that gives each unit its safe range.

mod digest;
mod latest;
mod log;
mod table;
mod units;

use std::process::ExitCode;

const USAGE: &str = "usage: froid check LOG...
       froid latest [--units FILE] LOG...
       froid digest [--units FILE] [--day YYYY-MM-DD] LOG...";

/// The units file froid reads when no --units is given: the one beside the exports.
const DEFAULT_UNITS: &str = "units.tsv";

/// Why a command stopped: a usage error (exit status 2) or a problem with the files (status 1).
pub enum Failure {
    Usage(String),
    Data(String),
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match run(&args) {
        Ok(code) => code,
        Err(Failure::Usage(msg)) => {
            eprintln!("froid: {msg}");
            eprintln!("{USAGE}");
            ExitCode::from(2)
        }
        Err(Failure::Data(msg)) => {
            eprintln!("froid: {msg}");
            ExitCode::from(1)
        }
    }
}

fn run(args: &[String]) -> Result<ExitCode, Failure> {
    let Some((command, rest)) = args.split_first() else {
        return Err(Failure::Usage("no command given".into()));
    };
    match command.as_str() {
        "check" => Ok(check(&Options::parse(rest, &[])?.logs)),
        "latest" => {
            let opts = Options::parse(rest, &["--units"])?;
            let units = units::read_file(opts.units())?;
            let readings = log::read_all(&opts.logs)?;
            print!("{}", latest::report(&units, &readings));
            Ok(ExitCode::SUCCESS)
        }
        "digest" => {
            let opts = Options::parse(rest, &["--units", "--day"])?;
            if let Some(day) = &opts.day {
                if !log::is_date(day) {
                    return Err(Failure::Usage(format!("--day wants a date like 2026-09-21, not {day:?}")));
                }
            }
            // Check everything first, so a bad file gets the same message here as from check and latest.
            units::read_file(opts.units())?;
            log::read_all(&opts.logs)?;
            digest::run(opts.units(), opts.day.as_deref(), &opts.logs)
        }
        "-h" | "--help" | "help" => {
            println!("{USAGE}");
            Ok(ExitCode::SUCCESS)
        }
        other => Err(Failure::Usage(format!("unknown command {other:?}"))),
    }
}

/// `froid check`: each export's size and span, or the first problem in it.
fn check(paths: &[String]) -> ExitCode {
    let mut ok = true;
    for path in paths {
        match log::read_file(path) {
            Ok(readings) if readings.is_empty() => println!("{path}: no readings"),
            Ok(readings) => {
                let mut units: Vec<&str> = readings.iter().map(|r| r.unit.as_str()).collect();
                units.sort_unstable();
                units.dedup();
                let first = readings.iter().map(|r| r.date.as_str()).min().unwrap_or_default();
                let last = readings.iter().map(|r| r.date.as_str()).max().unwrap_or_default();
                let plural = if units.len() == 1 { "" } else { "s" };
                println!("{path}: {} readings from {} unit{plural}, {first} to {last}", readings.len(), units.len());
            }
            Err(msg) => {
                eprintln!("froid: {msg}");
                ok = false;
            }
        }
    }
    if ok {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

struct Options {
    units: Option<String>,
    day: Option<String>,
    logs: Vec<String>,
}

impl Options {
    /// Options (only those in `allowed`, each with a value) and at least one log file; `--` ends the options.
    fn parse(args: &[String], allowed: &[&str]) -> Result<Options, Failure> {
        let mut opts = Options { units: None, day: None, logs: Vec::new() };
        let mut i = 0;
        while i < args.len() {
            let arg = &args[i];
            if arg == "--" {
                opts.logs.extend(args[i + 1..].iter().cloned());
                break;
            }
            if arg.starts_with("--") && arg.len() > 2 {
                if !allowed.contains(&arg.as_str()) {
                    return Err(Failure::Usage(format!("unknown option {arg}")));
                }
                let Some(value) = args.get(i + 1) else {
                    return Err(Failure::Usage(format!("{arg} needs a value")));
                };
                match arg.as_str() {
                    "--units" => opts.units = Some(value.clone()),
                    _ => opts.day = Some(value.clone()),
                }
                i += 2;
                continue;
            }
            opts.logs.push(arg.clone());
            i += 1;
        }
        if opts.logs.is_empty() {
            return Err(Failure::Usage("no log files given".into()));
        }
        Ok(opts)
    }

    fn units(&self) -> &str {
        self.units.as_deref().unwrap_or(DEFAULT_UNITS)
    }
}
