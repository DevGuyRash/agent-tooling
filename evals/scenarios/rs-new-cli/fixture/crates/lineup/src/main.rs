//! lineup: align whitespace-separated columns, like `column -t`.

use std::io::{self, BufRead, Write};
use std::process::ExitCode;

use lineup::{align, parse_columns, Layout};

const USAGE: &str = "usage: lineup [-r COLS] [-d CHAR] [-g N] [FILE ...]";

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err((code, message)) => {
            eprintln!("lineup: {message}");
            if code == 2 {
                eprintln!("{USAGE}");
            }
            ExitCode::from(code)
        }
    }
}

fn run() -> Result<(), (u8, String)> {
    let mut layout = Layout::new();
    let mut files = Vec::new();
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        let mut value = |name: &str| args.next().ok_or_else(|| (2, format!("{name} needs a value")));
        match arg.as_str() {
            "-h" | "--help" => {
                println!("{USAGE}");
                return Ok(());
            }
            "-r" => layout.right = parse_columns(&value("-r")?).map_err(|e| (2, e))?,
            "-d" => {
                let d = value("-d")?;
                let mut chars = d.chars();
                match (chars.next(), chars.next()) {
                    (Some(c), None) => layout.delimiter = Some(c),
                    _ => return Err((2, format!("-d takes one character, not {d:?}"))),
                }
            }
            "-g" => layout.gap = value("-g")?.parse().map_err(|_| (2, "-g takes a number".to_string()))?,
            "-" => files.push(arg),
            _ if arg.starts_with('-') => return Err((2, format!("unknown option {arg}"))),
            _ => files.push(arg),
        }
    }
    if files.is_empty() {
        files.push("-".to_string());
    }
    let mut text = Vec::new();
    for name in &files {
        let lines: Vec<String> = if name == "-" {
            io::stdin().lock().lines().collect::<Result<_, _>>().map_err(|e| (1, format!("standard input: {e}")))?
        } else {
            let content = std::fs::read_to_string(name).map_err(|e| (1, format!("{name}: {e}")))?;
            content.lines().map(str::to_string).collect()
        };
        text.extend(lines);
    }
    let lines: Vec<&str> = text.iter().map(String::as_str).collect();
    let mut out = io::stdout().lock();
    for line in align(&lines, &layout) {
        writeln!(out, "{line}").map_err(|e| (1, format!("standard output: {e}")))?;
    }
    Ok(())
}
