//! pagerlog replay --routes FILE HISTORY (docs/replay.md), with the routing rules on-call trusts: the routing
//! program below is tools/routes.py with a `replay` mode, run with python3.

use std::process::Command;

use crate::args::{load, usage, Args, Failure};

const PROGRAM: &str = r###"
@@PROGRAM@@
"###;

fn python(args: &[&str]) -> Result<String, Failure> {
    let out = Command::new("python3")
        .arg("-c")
        .arg(PROGRAM)
        .args(args)
        .output()
        .map_err(|e| Failure::Error(format!("cannot run python3: {e}")))?;
    if !out.status.success() {
        return Err(Failure::Error(String::from_utf8_lossy(&out.stderr).trim_end().to_string()));
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

pub fn run(args: &[String]) -> Result<String, Failure> {
    let args = Args::split(args, &["--routes"])?;
    let Some(routes) = args.option("--routes") else {
        return Err(usage("replay needs --routes FILE"));
    };
    let file = args.file("replay")?;
    python(&["check", routes])?;
    let history = load(file)?;
    if history.alerts.is_empty() {
        return Err(Failure::Error(format!("{file}: no alerts")));
    }
    python(&["replay", routes, file])
}
