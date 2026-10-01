//! envflat [--prefix NAME] [FILE]: write a JSON settings file as KEY=VALUE lines.

use std::io::{self, Read, Write};
use std::process::ExitCode;

const USAGE: &str = "usage: envflat [--prefix NAME] [FILE]";

fn usage_error(message: &str) -> ExitCode {
    eprintln!("envflat: {message}");
    eprintln!("{USAGE}");
    ExitCode::from(2)
}

fn fail(message: &str) -> ExitCode {
    eprintln!("envflat: {message}");
    ExitCode::from(1)
}

fn main() -> ExitCode {
    let mut prefix: Option<String> = None;
    let mut files: Vec<String> = Vec::new();
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--prefix" {
            match args.next() {
                Some(name) => prefix = Some(name),
                None => return usage_error("--prefix needs a NAME"),
            }
        } else if let Some(name) = arg.strip_prefix("--prefix=") {
            prefix = Some(name.to_string());
        } else if arg == "-h" || arg == "--help" {
            println!("{USAGE}");
            return ExitCode::SUCCESS;
        } else if arg.starts_with('-') && arg != "-" {
            return usage_error(&format!("unknown option {arg}"));
        } else {
            files.push(arg);
        }
    }
    if files.len() > 1 {
        return usage_error("more than one FILE");
    }
    let name = files.pop().unwrap_or_else(|| "-".to_string());
    let raw = if name == "-" {
        let mut buf = Vec::new();
        if let Err(e) = io::stdin().read_to_end(&mut buf) {
            return fail(&format!("cannot read standard input: {e}"));
        }
        buf
    } else {
        match std::fs::read(&name) {
            Ok(buf) => buf,
            Err(e) => return fail(&format!("cannot read {name}: {e}")),
        }
    };
    let Ok(text) = String::from_utf8(raw) else {
        return fail("invalid JSON: the input is not UTF-8");
    };
    match envflat::flatten(&text, prefix.as_deref()) {
        Ok(lines) => {
            let out: String = lines.iter().map(|l| format!("{l}\n")).collect();
            if io::stdout().write_all(out.as_bytes()).is_err() {
                return fail("cannot write standard output");
            }
            ExitCode::SUCCESS
        }
        Err(message) => fail(&message),
    }
}
