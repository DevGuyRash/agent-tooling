//! pagerlog: reports on the paging service's alert history exports.

mod args;
mod check;
mod receivers;
mod top;

use std::process::ExitCode;

use args::Failure;

const USAGE: &str = "usage: pagerlog check HISTORY
       pagerlog receivers [--sort alerts|name] HISTORY
       pagerlog top [--limit N] HISTORY";

fn main() -> ExitCode {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let Some((command, rest)) = argv.split_first() else {
        eprintln!("{USAGE}");
        return ExitCode::from(2);
    };
    let result = match command.as_str() {
        "check" => check::run(rest),
        "receivers" => receivers::run(rest),
        "top" => top::run(rest),
        "help" | "-h" | "--help" => Ok(format!("{USAGE}\n")),
        other => Err(Failure::Usage(format!("unknown command \"{other}\""))),
    };
    match result {
        Ok(text) => {
            print!("{text}");
            ExitCode::SUCCESS
        }
        Err(Failure::Usage(message)) => {
            eprintln!("pagerlog: {message}\n{USAGE}");
            ExitCode::from(2)
        }
        Err(Failure::Error(message)) => {
            eprintln!("pagerlog: {message}");
            ExitCode::from(1)
        }
    }
}
