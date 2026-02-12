//! Binary entrypoint for the deterministic PIASCS CLI.

use clap::Parser;
use piascs::cli::Cli;

fn main() {
    let cli = Cli::parse();
    match piascs::run(cli.command) {
        Ok(output) => {
            if !output.is_empty() {
                println!("{output}");
            }
        }
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}
