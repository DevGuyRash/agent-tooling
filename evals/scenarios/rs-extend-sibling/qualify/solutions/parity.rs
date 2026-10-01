//! td standings agrees with the website script (tools/standings.py) on points, Buchholz, and
//! Sonneborn-Berger for finished tournaments, where the two count the same rounds.

use std::collections::BTreeMap;
use std::path::PathBuf;
use std::process::Command;

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// start number -> (points, Buchholz, Sonneborn-Berger), as printed.
type Values = BTreeMap<String, (String, String, String)>;

fn from_td(file: &str) -> Values {
    let out = Command::new(env!("CARGO_BIN_EXE_td"))
        .args(["standings", "--tiebreaks", "bh,sb", file])
        .output()
        .unwrap();
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    String::from_utf8(out.stdout)
        .unwrap()
        .lines()
        .skip(3)
        .map(|line| {
            let f: Vec<&str> = line.split_whitespace().collect();
            let n = f.len();
            (f[1].to_string(), (f[n - 3].to_string(), f[n - 2].to_string(), f[n - 1].to_string()))
        })
        .collect()
}

fn from_script(file: &str) -> Values {
    let out = Command::new("python3")
        .arg(repo().join("tools/standings.py"))
        .args(["--tsv", file])
        .output()
        .expect("python3 runs the website script");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    String::from_utf8(out.stdout)
        .unwrap()
        .lines()
        .skip(1)
        .map(|line| {
            let f: Vec<&str> = line.split('\t').collect();
            (f[1].to_string(), (f[4].to_string(), f[5].to_string(), f[6].to_string()))
        })
        .collect()
}

#[test]
fn finished_tournaments_match_the_website() {
    for name in ["summer-blitz-2026.trn", "spring-rapid-2026.trn"] {
        let file = repo().join("tournaments").join(name);
        let file = file.to_str().unwrap();
        assert_eq!(from_td(file), from_script(file), "{name}");
    }
}
