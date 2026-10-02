use std::process::Command;

fn startline(args: &[&str]) -> (i32, String, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_startline")).args(args).output().unwrap();
    (out.status.code().unwrap_or(-1), String::from_utf8(out.stdout).unwrap(), String::from_utf8(out.stderr).unwrap())
}

#[test]
fn one_start() {
    let (code, out, err) = startline(&["sequence", "14:00:00"]);
    assert_eq!(code, 0, "{err}");
    assert_eq!(
        out,
        "\
time      start  signal
13:55:00      1  warning
13:56:00      1  preparatory
13:59:00      1  one minute
14:00:00      1  start
"
    );
}

#[test]
fn rolling_starts_share_the_start_and_warning_signal() {
    let (code, out, _) = startline(&["sequence", "14:00:00", "--starts", "3"]);
    assert_eq!(code, 0);
    let lines: Vec<&str> = out.lines().collect();
    assert_eq!(lines.len(), 13);
    assert_eq!(lines[4], "14:00:00      1  start");
    assert_eq!(lines[5], "14:00:00      2  warning");
    assert_eq!(lines[12], "14:10:00      3  start");
}

#[test]
fn a_longer_gap() {
    let (_, out, _) = startline(&["sequence", "--gap", "10", "11:30:00", "--starts", "2"]);
    assert_eq!(out.lines().nth(5), Some("11:35:00      2  warning"));
}

#[test]
fn usage_and_range_errors() {
    for args in [&[][..], &["start"], &["sequence"], &["sequence", "2pm"], &["sequence", "14:00:00", "--starts", "0"],
                 &["sequence", "14:00:00", "--gap"], &["sequence", "14:00:00", "--fast"], &["sequence", "14:00:00", "15:00:00"]] {
        let (code, _, err) = startline(args);
        assert_eq!(code, 2, "{args:?}");
        assert!(err.starts_with("startline: ") && err.contains("usage: startline"), "{err}");
    }
    let (code, _, err) = startline(&["sequence", "00:03:00"]);
    assert_eq!((code, err.as_str()), (1, "startline: the first warning signal would be before midnight\n"));
}
