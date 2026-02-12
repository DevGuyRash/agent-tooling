//! Binary entrypoint for the deterministic PCA CLI.

use clap::Parser;
use pca::cli::Cli;

fn main() {
    let cli = Cli::parse();
    match pca::run(cli.command) {
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
