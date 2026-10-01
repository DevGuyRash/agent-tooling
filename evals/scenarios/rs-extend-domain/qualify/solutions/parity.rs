//! pagerlog replay agrees with tools/routes.py, which on-call uses to try routing changes: every alert in the
//! repository's history export goes through `routes.py test`, and the receivers it names add up to replay's
//! After column.

use std::collections::BTreeMap;
use std::path::PathBuf;
use std::process::Command;

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

#[test]
fn after_column_matches_routes_py() {
    let root = repo();
    let routes = root.join("routing/main.routes");
    let history = root.join("history/2026-q3.tsv");
    let text = std::fs::read_to_string(&history).unwrap();
    let mut expected: BTreeMap<String, usize> = BTreeMap::new();
    for line in text.lines().skip(1).filter(|l| !l.is_empty()) {
        let fields: Vec<&str> = line.split('\t').collect();
        let mut cmd = Command::new("python3");
        cmd.arg(root.join("tools/routes.py")).arg("test").arg(&routes).args(["--at", fields[0]]);
        cmd.arg(format!("alertname={}", fields[1]));
        if fields[3] != "-" {
            cmd.args(fields[3].split(','));
        }
        let out = cmd.output().expect("python3 runs");
        assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
        for receiver in String::from_utf8(out.stdout).unwrap().lines() {
            *expected.entry(receiver.to_string()).or_default() += 1;
        }
    }
    let out = Command::new(env!("CARGO_BIN_EXE_pagerlog"))
        .arg("replay")
        .arg("--routes")
        .arg(&routes)
        .arg(&history)
        .output()
        .unwrap();
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let report = String::from_utf8(out.stdout).unwrap();
    let mut got: BTreeMap<String, usize> = BTreeMap::new();
    for line in report.lines().skip(3).take_while(|l| !l.is_empty()) {
        let cells: Vec<&str> = line.split_whitespace().collect();
        let after: usize = cells[2].parse().unwrap();
        if after > 0 {
            got.insert(cells[0].to_string(), after);
        }
    }
    assert_eq!(got, expected);
}
