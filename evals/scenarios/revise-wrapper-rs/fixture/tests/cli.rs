//! froid's command line, run on the sample exports in data/.

use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn froid(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_froid")).args(args).current_dir(root()).output().expect("froid runs")
}

fn stdout(out: &Output) -> String {
    String::from_utf8(out.stdout.clone()).expect("UTF-8 output")
}

fn stderr(out: &Output) -> String {
    String::from_utf8_lossy(&out.stderr).into_owned()
}

fn scratch(name: &str, text: &str) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR")).join("cli");
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join(name);
    std::fs::write(&path, text).unwrap();
    path
}

#[test]
fn check_summarises_each_export() {
    let out = froid(&["check", "data/2026-09-21.log", "data/2026-09-22.log"]);
    assert!(out.status.success(), "{}", stderr(&out));
    assert_eq!(
        stdout(&out),
        "data/2026-09-21.log: 240 readings from 5 units, 2026-09-21 to 2026-09-21\n\
         data/2026-09-22.log: 240 readings from 5 units, 2026-09-22 to 2026-09-22\n"
    );
}

#[test]
fn check_names_the_bad_line_and_goes_on() {
    let bad = scratch("bad.log", "# export\n2026-09-21T06:00Z\tfrigo-lait\t3.1\n2026-09-21T06:30Z\tfrigo-lait\t3,1\n");
    let out = froid(&["check", bad.to_str().unwrap(), "data/2026-09-22.log"]);
    assert_eq!(out.status.code(), Some(1));
    assert!(stderr(&out).contains("bad.log:3: bad temperature \"3,1\""), "{}", stderr(&out));
    assert_eq!(stdout(&out), "data/2026-09-22.log: 240 readings from 5 units, 2026-09-22 to 2026-09-22\n");
}

#[test]
fn latest_reading_per_unit() {
    let out = froid(&["latest", "--units", "data/units.tsv", "data/2026-09-21.log", "data/2026-09-22.log"]);
    assert!(out.status.success(), "{}", stderr(&out));
    assert_eq!(
        stdout(&out),
        "unit            time               temp  status\n\
         frigo-entrée    2026-09-22 23:30    3.7  ok\n\
         chambre-froide  2026-09-22 23:30    1.7  ok\n\
         congélateur-2   2026-09-22 23:30  -20.5  ok\n\
         congélateur-1   2026-09-22 23:30  -21.1  ok\n\
         frigo-lait      2026-09-22 23:30    2.8  ok\n"
    );
}

#[test]
fn latest_without_a_range() {
    let log = scratch("cave.log", "2026-09-21T06:00Z\tfrigo-cave\t9.4\n2026-09-21T06:00Z\tfrigo-lait\t4.1\n");
    let out = froid(&["latest", "--units", "data/units.tsv", log.to_str().unwrap()]);
    assert!(out.status.success(), "{}", stderr(&out));
    assert_eq!(
        stdout(&out),
        "unit        time              temp  status\n\
         frigo-cave  2026-09-21 06:00   9.4  no range\n\
         frigo-lait  2026-09-21 06:00   4.1  too warm\n"
    );
}

#[test]
fn digest_matches_the_docs_example() {
    let out = froid(&["digest", "--units", "data/units.tsv", "--day", "2026-09-21", "data/2026-09-21.log"]);
    assert!(out.status.success(), "{}", stderr(&out));
    assert_eq!(
        stdout(&out),
        "unit            day          n    min    max   mean  median  out  worst\n\
         frigo-entrée    2026-09-21  48    2.3    4.9    3.1     3.0    3  4.9 at 13:00\n\
         chambre-froide  2026-09-21  48    1.8    2.7    2.2     2.3    0  -\n\
         congélateur-2   2026-09-21  48  -21.1  -17.4  -20.3   -20.4    2  -17.4 at 15:00\n\
         congélateur-1   2026-09-21  48  -22.0  -17.8  -21.2   -21.3    1  -17.8 at 03:00\n\
         frigo-lait      2026-09-21  48    2.2    3.4    2.6     2.5    0  -\n\
         \n\
         5 unit-days, 6 readings out of range\n"
    );
}

#[test]
fn digest_refuses_a_bad_export_like_check() {
    let bad = scratch("short.log", "2026-09-21T06:00Z\tfrigo-lait\n");
    let out = froid(&["digest", "--units", "data/units.tsv", bad.to_str().unwrap()]);
    assert_eq!(out.status.code(), Some(1));
    assert!(stderr(&out).contains("short.log:1: expected time, unit, and temperature"), "{}", stderr(&out));
    assert_eq!(stdout(&out), "");
}

#[test]
fn usage_errors_exit_2() {
    for args in [&[][..], &["digest"][..], &["digest", "--day", "21/09/2026", "data/2026-09-21.log"][..], &["latest", "--colour", "x", "y"][..]] {
        let out = froid(args);
        assert_eq!(out.status.code(), Some(2), "{args:?}");
        assert!(stderr(&out).contains("usage: froid"), "{args:?}");
    }
}
