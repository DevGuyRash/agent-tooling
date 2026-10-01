//! td: the arbiter's tool for Rookhaven tournament files.

mod args;
mod card;
mod check;
mod players;

use std::process::ExitCode;

use args::Failure;

const USAGE: &str = "usage: td check FILE
       td players [--by no|name|rating] FILE
       td card FILE NO";

fn main() -> ExitCode {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let Some((command, rest)) = argv.split_first() else {
        eprintln!("{USAGE}");
        return ExitCode::from(2);
    };
    let result = match command.as_str() {
        "check" => check::run(rest),
        "players" => players::run(rest),
        "card" => card::run(rest),
        "help" | "-h" | "--help" => Ok(format!("{USAGE}\n")),
        other => Err(Failure::Usage(format!("unknown command \"{other}\""))),
    };
    match result {
        Ok(text) => {
            print!("{text}");
            ExitCode::SUCCESS
        }
        Err(Failure::Usage(message)) => {
            eprintln!("td: {message}\n{USAGE}");
            ExitCode::from(2)
        }
        Err(Failure::Error(message)) => {
            eprintln!("td: {message}");
            ExitCode::from(1)
        }
    }
}
