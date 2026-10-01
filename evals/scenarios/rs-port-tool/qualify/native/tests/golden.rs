//! The reports the nightly job diffs and the dashboard scrapes, against the Python version's golden files.

use std::path::PathBuf;
use std::process::Command;

fn data_dir() -> PathBuf {
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    [manifest.join("tests/data"), manifest.join("../tests/data")]
        .into_iter()
        .find(|d| d.join("sample.log").is_file())
        .expect("tests/data with the golden files")
}

fn golden(expected: &str, args: &[&str]) {
    let dir = data_dir();
    let out = Command::new(env!("CARGO_BIN_EXE_reqstat")).args(args).arg(dir.join("sample.log")).output().unwrap();
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let want = std::fs::read_to_string(dir.join(expected)).unwrap();
    let got = String::from_utf8(out.stdout).unwrap();
    let got = got.replace(dir.join("sample.log").to_str().unwrap(), "tests/data/sample.log");
    assert_eq!(got, want);
}

#[test]
fn route_table() {
    golden("sample-route.txt", &[]);
}

#[test]
fn path_csv_by_p95() {
    golden("sample-path-p95.csv", &["--by", "path", "--format", "csv", "--sort", "p95"]);
}

#[test]
fn status_window() {
    golden("sample-status-window.txt", &["--by", "status", "--since", "2026-09-14T08:00:05Z", "--until", "2026-09-14T08:00:20Z"]);
}

#[test]
fn strict_reports_file_and_line() {
    let file = data_dir().join("sample.log");
    let out = Command::new(env!("CARGO_BIN_EXE_reqstat")).arg("--strict").arg(&file).output().unwrap();
    assert_eq!(out.status.code(), Some(1));
    assert!(out.stdout.is_empty());
    assert!(String::from_utf8_lossy(&out.stderr).contains("sample.log:12:"));
}
