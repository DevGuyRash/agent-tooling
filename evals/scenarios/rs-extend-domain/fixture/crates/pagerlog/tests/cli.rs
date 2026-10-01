//! pagerlog's commands, run as on-call runs them.

use std::path::PathBuf;
use std::process::{Command, Output};

// 2026-07-04 and 2026-07-05 are a Saturday and a Sunday.
const EXPORT: &str = "time\talert\treceivers\tlabels
2026-07-03T09:15:00Z\tApiLatency\tpayments-oncall\tenv=prod,service=checkout,team=payments
2026-07-03T23:40:12Z\tDiskFull\tstorage-oncall,dba-oncall\tservice=db-orders,severity=critical,team=storage
2026-07-04T02:05:00Z\tDiskFull\tstorage-oncall\tservice=blob-eu,severity=warning,team=storage
2026-07-05T14:00:00Z\tCertExpiry\tplatform-tickets\t-
2026-07-01T06:59:59Z\tApiLatency\tpayments-oncall\tenv=prod,service=checkout,team=payments
2026-07-06T07:00:00Z\tQueueDepth\tpayments-oncall\tqueue=refunds,team=payments
";

fn file(name: &str, text: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!("pagerlog-cli-{}-{name}.tsv", std::process::id()));
    std::fs::write(&path, text).unwrap();
    path
}

fn pagerlog(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_pagerlog")).args(args).output().unwrap()
}

fn stdout(o: &Output) -> String {
    String::from_utf8(o.stdout.clone()).unwrap()
}

fn stderr(o: &Output) -> String {
    String::from_utf8(o.stderr.clone()).unwrap()
}

#[test]
fn check_says_what_the_export_covers() {
    let f = file("check", EXPORT);
    let o = pagerlog(&["check", f.to_str().unwrap()]);
    assert_eq!(o.status.code(), Some(0), "{}", stderr(&o));
    assert_eq!(stdout(&o), format!("{}: ok, 6 alerts from 2026-07-01 to 2026-07-06\n", f.display()));
}

#[test]
fn check_an_empty_export() {
    let f = file("empty", "time\talert\treceivers\tlabels\n");
    let o = pagerlog(&["check", f.to_str().unwrap()]);
    assert_eq!(stdout(&o), format!("{}: ok, no alerts\n", f.display()));
}

#[test]
fn check_names_the_line_of_a_problem() {
    let f = file("bad", &EXPORT.replace("2026-07-05T14:00:00Z", "2026-07-05T14:00Z"));
    let o = pagerlog(&["check", f.to_str().unwrap()]);
    assert_eq!(o.status.code(), Some(1));
    assert_eq!(stdout(&o), "");
    assert_eq!(stderr(&o), format!("pagerlog: {}: line 5: bad time \"2026-07-05T14:00Z\"\n", f.display()));
}

#[test]
fn missing_file() {
    let o = pagerlog(&["check", "/nonexistent/q3.tsv"]);
    assert_eq!(o.status.code(), Some(1));
    assert!(stderr(&o).starts_with("pagerlog: /nonexistent/q3.tsv: "), "{}", stderr(&o));
}

#[test]
fn receivers_by_alerts() {
    let f = file("receivers", EXPORT);
    let o = pagerlog(&["receivers", f.to_str().unwrap()]);
    assert_eq!(o.status.code(), Some(0), "{}", stderr(&o));
    assert_eq!(
        stdout(&o),
        "Receiver          Alerts  Night  Weekend
payments-oncall        3      1        0
storage-oncall         2      2        1
dba-oncall             1      1        0
platform-tickets       1      0        1
"
    );
}

#[test]
fn receivers_by_name() {
    let f = file("receivers-name", EXPORT);
    let o = pagerlog(&["receivers", f.to_str().unwrap(), "--sort", "name"]);
    let names: Vec<String> = stdout(&o).lines().skip(1).map(|l| l.split(' ').next().unwrap().to_string()).collect();
    assert_eq!(names, ["dba-oncall", "payments-oncall", "platform-tickets", "storage-oncall"]);
}

#[test]
fn top_alerts() {
    let f = file("top", EXPORT);
    let o = pagerlog(&["top", "--limit", "2", f.to_str().unwrap()]);
    assert_eq!(o.status.code(), Some(0), "{}", stderr(&o));
    assert_eq!(
        stdout(&o),
        "Alerts  Alert       Receivers
     2  ApiLatency  payments-oncall
     2  DiskFull    dba-oncall, storage-oncall
"
    );
}

#[test]
fn usage_errors_exit_2() {
    let f = file("usage", EXPORT);
    let path = f.to_str().unwrap();
    for args in [
        vec!["receivers", "--sort", "night", path],
        vec!["top", "--limit", "0", path],
        vec!["top", "--limit", "+3", path],
        vec!["top", path, "--limit"],
        vec!["top", "--limit", "2", "--limit", "3", path],
        vec!["check"],
        vec!["check", path, path],
        vec!["check", "--verbose", path],
        vec!["purge", path],
    ] {
        let o = pagerlog(&args);
        assert_eq!(o.status.code(), Some(2), "{args:?}");
        assert_eq!(stdout(&o), "", "{args:?}");
        assert!(stderr(&o).starts_with("pagerlog: "), "{args:?}: {}", stderr(&o));
    }
}
