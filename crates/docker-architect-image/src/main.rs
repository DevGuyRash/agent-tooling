//! Binary entrypoint for the deterministic docker-architect-image CLI.

use architect_core::cli::Command;
use architect_core::{output_has_blocked_violations, run, SkillVariant};
use clap::Parser;

#[derive(Debug, Parser)]
#[command(
    name = "docker-architect-image",
    about = "Deterministic helper for docker image architecture skill"
)]
struct Cli {
    /// Command to execute.
    #[command(subcommand)]
    command: Command,
}

fn main() {
    let cli = Cli::parse();
    let should_gate_blocked_policy = matches!(&cli.command, Command::PolicyCheck(_));
    match run(cli.command, SkillVariant::Image) {
        Ok(output) => {
            if !output.is_empty() {
                println!("{output}");
            }
            if should_gate_blocked_policy {
                match output_has_blocked_violations(&output) {
                    Ok(true) => std::process::exit(2),
                    Ok(false) => {}
                    Err(error) => {
                        eprintln!("{error}");
                        std::process::exit(1);
                    }
                }
            }
        }
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(1);
        }
    }
}
