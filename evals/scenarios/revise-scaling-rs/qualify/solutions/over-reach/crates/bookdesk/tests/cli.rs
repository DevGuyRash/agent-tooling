use std::path::PathBuf;
use std::process::{Command, Output};

fn data(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/data")
        .join(name)
}

fn bookdesk(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_bookdesk"))
        .args(args)
        .output()
        .unwrap()
}

fn text(bytes: &[u8]) -> String {
    String::from_utf8(bytes.to_vec()).unwrap()
}

#[test]
fn clashes_for_a_kingsgate_week() {
    let path = data("kingsgate-2026-w38.csv");
    let out = bookdesk(&["clashes", path.to_str().unwrap()]);
    assert_eq!(out.status.code(), Some(0), "{}", text(&out.stderr));
    assert_eq!(
        text(&out.stdout),
        std::fs::read_to_string(data("kingsgate-2026-w38.clashes.txt")).unwrap()
    );
}

#[test]
fn back_to_back_and_cancelled_bookings_do_not_clash() {
    let path = data("kingsgate-2026-w38.csv");
    let out = text(&bookdesk(&["clashes", path.to_str().unwrap()]).stdout);
    assert!(
        !out.contains("B26-0003126"),
        "back to back on the same lane"
    );
    assert!(!out.contains("B26-0003131"), "cancelled");
    assert!(!out.contains("B26-0003140"), "cancelled");
    assert!(!out.contains("B26-0003161"), "same time, another lane");
}

#[test]
fn no_clashes() {
    let dir = std::env::temp_dir().join(format!("bookdesk-cli-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("quiet.csv");
    std::fs::write(&path, "ref,facility,date,start,end,status,booked_by\nB26-0000001,KGS-SQ1,2026-09-14,18:00,18:40,confirmed,M1\n").unwrap();
    let out = bookdesk(&["clashes", path.to_str().unwrap()]);
    std::fs::remove_dir_all(&dir).unwrap();
    assert_eq!(text(&out.stdout), "no clashes\n");
}

#[test]
fn usage_per_facility_and_centre() {
    let path = data("kingsgate-2026-w38.csv");
    let out = bookdesk(&["usage", path.to_str().unwrap()]);
    assert_eq!(out.status.code(), Some(0));
    assert_eq!(
        text(&out.stdout),
        std::fs::read_to_string(data("kingsgate-2026-w38.usage.txt")).unwrap()
    );
    let other = bookdesk(&["usage", path.to_str().unwrap(), "--centre", "RVP"]);
    assert_eq!(text(&other.stdout), "all                  0.0h\n");
}

#[test]
fn a_bad_export_lists_its_problems_and_prints_nothing() {
    let path = data("bad-export.csv");
    for command in ["clashes", "usage", "check"] {
        let out = bookdesk(&[command, path.to_str().unwrap()]);
        assert_eq!(out.status.code(), Some(1));
        assert_eq!(text(&out.stdout), "");
        let err = text(&out.stderr);
        assert!(
            err.contains("bad-export.csv: line 6: booking B26-0003101 is already on line 2\n"),
            "{err}"
        );
        assert!(err.ends_with("bad-export.csv: 7 problems\n"), "{err}");
    }
}

#[test]
fn check_counts_bookings() {
    let path = data("kingsgate-2026-w38.csv");
    let out = bookdesk(&["check", path.to_str().unwrap()]);
    assert!(text(&out.stdout).ends_with("kingsgate-2026-w38.csv: 21 bookings, all lines valid\n"));
}

#[test]
fn usage_errors_exit_2() {
    assert_eq!(bookdesk(&[]).status.code(), Some(2));
    assert_eq!(bookdesk(&["clashes"]).status.code(), Some(2));
    assert_eq!(
        bookdesk(&["clashes", "a.csv", "--fast", "yes"])
            .status
            .code(),
        Some(2)
    );
    assert_eq!(bookdesk(&["report", "a.csv"]).status.code(), Some(2));
}

#[test]
fn an_unreadable_export_exits_1() {
    let out = bookdesk(&["clashes", "/nonexistent/upcoming.csv"]);
    assert_eq!(out.status.code(), Some(1));
    assert!(text(&out.stderr).starts_with("bookdesk: cannot read /nonexistent/upcoming.csv"));
}
