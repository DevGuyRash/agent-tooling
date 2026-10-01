//! The check's own copy of lineup's behavior, through its binary: what the fixture's unit tests in
//! crates/lineup/src/lib.rs establish, so weakening or deleting those tests does not hide a change to lineup.
//! check.py places this file in crates/lineup/tests/ of its copy of the agent's workspace. Expected outputs
//! are the fixture lineup's own.

use std::io::Write;
use std::process::{Command, Stdio};

fn lineup(args: &[&str], input: &str) -> (i32, String) {
    let mut child = Command::new(env!("CARGO_BIN_EXE_lineup"))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(input.as_bytes()).unwrap();
    let out = child.wait_with_output().unwrap();
    (out.status.code().unwrap_or(-1), String::from_utf8(out.stdout).unwrap())
}

fn assert_lineup(args: &[&str], input: &str, expected: &str) {
    assert_eq!(lineup(args, input), (0, expected.to_string()), "lineup {args:?} on {input:?}");
}

#[test]
fn ragged_columns_left_aligned() {
    assert_lineup(&[], "name size\na.txt 12\nlonger-name.tar.gz 4096\n",
                  "name                size\na.txt               12\nlonger-name.tar.gz  4096\n");
}

#[test]
fn selected_columns_right_aligned() {
    assert_lineup(&["-r", "2"], "name size\na.txt 12\nb 4096\n", "name   size\na.txt    12\nb      4096\n");
}

#[test]
fn comments_and_blank_lines_pass_through() {
    assert_lineup(&[], "# header\nx 1\n\nyy 22\n", "# header\nx   1\n\nyy  22\n");
}

#[test]
fn delimiter_keeps_empty_cells() {
    assert_lineup(&["-d", ","], "a,,c\ndd,e,f\n", "a      c\ndd  e  f\n");
}

#[test]
fn widths_count_characters() {
    assert_lineup(&[], "caf\u{e9} 1\nab 2\n", "caf\u{e9}  1\nab    2\n");
}

#[test]
fn column_list_in_any_order() {
    assert_lineup(&["-r", "3,1"], "a bb c\nddd e ffff\n", "  a  bb     c\nddd  e   ffff\n");
}

#[test]
fn tabs_and_space_runs_separate_cells() {
    assert_lineup(&[], "k\t\tv  w\nkey value\n", "k    v      w\nkey  value\n");
}

#[test]
fn bad_column_lists_are_usage_errors() {
    assert_eq!(lineup(&["-r", "0"], "").0, 2);
    assert_eq!(lineup(&["-r", "x"], "").0, 2);
}
