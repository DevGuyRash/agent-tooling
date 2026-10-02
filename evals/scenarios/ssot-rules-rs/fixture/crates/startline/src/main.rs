//! `startline`: what the race officer needs on the start line.

mod sequence;

use race::Clock;
use std::process::ExitCode;

const USAGE: &str = "usage: startline sequence START [--starts N] [--gap MINUTES]";

enum Failure {
    Usage(String),
    Run(String),
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match run(&args) {
        Ok(out) => {
            print!("{out}");
            ExitCode::SUCCESS
        }
        Err(Failure::Usage(message)) => {
            eprintln!("startline: {message}\n{USAGE}");
            ExitCode::from(2)
        }
        Err(Failure::Run(message)) => {
            eprintln!("startline: {message}");
            ExitCode::from(1)
        }
    }
}

fn run(args: &[String]) -> Result<String, Failure> {
    match args.first().map(String::as_str) {
        Some("sequence") => sequence(&args[1..]),
        Some(other) => Err(Failure::Usage(format!("unknown command {other:?}"))),
        None => Err(Failure::Usage("no command".to_string())),
    }
}

/// A whole number from `min` to `max`, for an option's value.
fn number(option: &str, value: Option<&String>, min: u32, max: u32) -> Result<u32, Failure> {
    let value = value.ok_or_else(|| Failure::Usage(format!("{option} needs a value")))?;
    match value.parse::<u32>() {
        Ok(n) if (min..=max).contains(&n) && !value.starts_with('+') => Ok(n),
        _ => Err(Failure::Usage(format!("{option} must be a whole number from {min} to {max}, not {value:?}"))),
    }
}

fn sequence(args: &[String]) -> Result<String, Failure> {
    let (mut starts, mut gap, mut first) = (1, 5, None);
    let mut it = args.iter();
    while let Some(arg) = it.next() {
        match arg.as_str() {
            "--starts" => starts = number("--starts", it.next(), 1, 9)?,
            "--gap" => gap = number("--gap", it.next(), 1, 60)?,
            a if a.starts_with('-') => return Err(Failure::Usage(format!("unknown option {a:?}"))),
            a if first.is_none() => {
                first = Some(Clock::parse(a).ok_or_else(|| Failure::Usage(format!("START must be HH:MM:SS, not {a:?}")))?)
            }
            a => return Err(Failure::Usage(format!("unexpected argument {a:?}"))),
        }
    }
    let first = first.ok_or_else(|| Failure::Usage("sequence needs the first start time".to_string()))?;
    sequence::table(first, starts, gap).map_err(Failure::Run)
}
