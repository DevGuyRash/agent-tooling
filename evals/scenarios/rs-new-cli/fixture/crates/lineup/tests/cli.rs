use std::io::Write;
use std::process::{Command, Stdio};

fn lineup(args: &[&str], input: &str) -> (i32, String, String) {
    let mut child = Command::new(env!("CARGO_BIN_EXE_lineup"))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(input.as_bytes()).unwrap();
    let out = child.wait_with_output().unwrap();
    (out.status.code().unwrap(), String::from_utf8(out.stdout).unwrap(), String::from_utf8(out.stderr).unwrap())
}

#[test]
fn aligns_standard_input() {
    let (code, out, _) = lineup(&["-r", "2"], "host load\nweb-1 0.42\ndb-primary 12.07\n");
    assert_eq!(code, 0);
    assert_eq!(out, "host         load\nweb-1        0.42\ndb-primary  12.07\n");
}

#[test]
fn custom_gap_and_delimiter() {
    let (code, out, _) = lineup(&["-d", ";", "-g", "1"], "a;bb;c\nddd;e;f\n");
    assert_eq!(code, 0);
    assert_eq!(out, "a   bb c\nddd e  f\n");
}

#[test]
fn usage_errors_exit_2() {
    assert_eq!(lineup(&["--frobnicate"], "").0, 2);
    assert_eq!(lineup(&["-r", "0"], "").0, 2);
    assert_eq!(lineup(&["-d", "ab"], "").0, 2);
}

#[test]
fn missing_file_exits_1() {
    let (code, out, err) = lineup(&["/nonexistent/lineup-input"], "");
    assert_eq!(code, 1);
    assert!(out.is_empty());
    assert!(err.starts_with("lineup: "));
}
