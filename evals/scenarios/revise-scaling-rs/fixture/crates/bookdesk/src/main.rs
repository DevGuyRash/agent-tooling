//! bookdesk COMMAND EXPORT.csv: the front desks' reports from the booking export. See README.md.

mod clashes;
mod usage;

use booking::Booking;
use std::io::Write;
use std::process::ExitCode;

const USAGE: &str = "usage: bookdesk clashes EXPORT.csv
       bookdesk usage EXPORT.csv [--centre CODE]
       bookdesk check EXPORT.csv
";

enum Failure {
    Usage(String),
    File(String),
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match run(&args) {
        Ok(text) => {
            let mut stdout = std::io::stdout().lock();
            let _ = stdout.write_all(text.as_bytes());
            let _ = stdout.flush();
            ExitCode::SUCCESS
        }
        Err(Failure::Usage(message)) => {
            eprint!("bookdesk: {message}\n{USAGE}");
            ExitCode::from(2)
        }
        Err(Failure::File(message)) => {
            eprintln!("bookdesk: {message}");
            ExitCode::from(1)
        }
    }
}

/// The command's arguments: one export file, and the options it allows.
fn arguments<'a>(
    args: &'a [String],
    allowed: &[&str],
) -> Result<(&'a str, Vec<(&'a str, &'a str)>), Failure> {
    let mut files = Vec::new();
    let mut options = Vec::new();
    let mut rest = args.iter();
    while let Some(arg) = rest.next() {
        if arg.starts_with("--") {
            if !allowed.contains(&arg.as_str()) {
                return Err(Failure::Usage(format!("unknown option {arg}")));
            }
            let value = rest
                .next()
                .ok_or_else(|| Failure::Usage(format!("{arg} needs a value")))?;
            options.push((arg.as_str(), value.as_str()));
        } else {
            files.push(arg.as_str());
        }
    }
    match files[..] {
        [file] => Ok((file, options)),
        _ => Err(Failure::Usage("expected one export file".to_string())),
    }
}

fn load(path: &str) -> Result<Vec<Booking>, Failure> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| Failure::File(format!("cannot read {path}: {e}")))?;
    booking::parse_export(&text).map_err(|problems| {
        for p in &problems {
            eprintln!("bookdesk: {path}: {p}");
        }
        let noun = if problems.len() == 1 {
            "problem"
        } else {
            "problems"
        };
        Failure::File(format!("{path}: {} {noun}", problems.len()))
    })
}

fn run(args: &[String]) -> Result<String, Failure> {
    let Some((command, rest)) = args.split_first() else {
        return Err(Failure::Usage("no command".to_string()));
    };
    match command.as_str() {
        "clashes" => {
            let (path, _) = arguments(rest, &[])?;
            let bookings = load(path)?;
            let pairs = clashes::find_clashes(&bookings);
            Ok(clashes::report(&bookings, &pairs))
        }
        "usage" => {
            let (path, options) = arguments(rest, &["--centre"])?;
            let bookings = load(path)?;
            Ok(usage::report(&bookings, options.last().map(|&(_, v)| v)))
        }
        "check" => {
            let (path, _) = arguments(rest, &[])?;
            let bookings = load(path)?;
            Ok(format!(
                "{path}: {} bookings, all lines valid\n",
                bookings.len()
            ))
        }
        other => Err(Failure::Usage(format!("unknown command {other}"))),
    }
}
