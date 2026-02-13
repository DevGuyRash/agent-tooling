//! Binary entrypoint for the deterministic PIASCS CLI.

use architect_core::cli::Command;
use architect_core::{run, SkillVariant};
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "piascs",
    about = "Deterministic helper for image architecture skill"
)]
struct Cli {
    /// Command to execute.
    #[command(subcommand)]
    command: Command,
}

fn main() {
    let cli = Cli::parse();
    match run(cli.command, SkillVariant::Piascs) {
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
