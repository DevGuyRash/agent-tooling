use std::io::Write;
use std::process::{Command, Stdio};

fn envflat(args: &[&str], input: &str) -> (i32, String, String) {
    let mut child = Command::new(env!("CARGO_BIN_EXE_envflat"))
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
fn reads_standard_input() {
    assert_eq!(envflat(&["--prefix", "app"], r#"{"a": {"b": [1, "x y"]}}"#), (0, "APP__A__B__0=1\nAPP__A__B__1='x y'\n".into(), String::new()));
}

#[test]
fn errors_print_nothing() {
    let (code, out, err) = envflat(&[], r#"{"a": 1, "b": {"c": "x\u0001"}}"#);
    assert_eq!((code, out.as_str()), (1, ""));
    assert!(err.starts_with("envflat: "));
}

#[test]
fn usage_errors_exit_2() {
    assert_eq!(envflat(&["--pretty"], "{}").0, 2);
    assert_eq!(envflat(&["--prefix"], "{}").0, 2);
    assert_eq!(envflat(&["a.json", "b.json"], "{}").0, 2);
}
