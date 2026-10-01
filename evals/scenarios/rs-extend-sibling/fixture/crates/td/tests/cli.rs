//! td's commands, run as a user runs them.

use std::path::PathBuf;
use std::process::{Command, Output};

const LEAGUE: &str = "\
# Rookhaven Chess Club
event Test League
rounds 4

player 1 2105 Lindqvist, Mia
player 2 1987 Okafor, Chidi
player 3 1862 Šimić, Luka
player 4 0 Price, Nora
player 5 1650 Haddad, Rami

round 1
1 3 1-0
2 4 1/2
bye 5 full

round 2
4 1 0-1
5 2 -+
bye 3 half

round 3
1 2 *
3 5 *
bye 4 zero
";

fn file(name: &str, text: &str) -> PathBuf {
    let path = std::env::temp_dir().join(format!("td-cli-{}-{name}.trn", std::process::id()));
    std::fs::write(&path, text).unwrap();
    path
}

fn td(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_td"))
        .args(args)
        .output()
        .unwrap()
}

fn stdout(o: &Output) -> String {
    String::from_utf8(o.stdout.clone()).unwrap()
}

fn stderr(o: &Output) -> String {
    String::from_utf8(o.stderr.clone()).unwrap()
}

#[test]
fn check_reports_how_far_the_file_goes() {
    let f = file("check", LEAGUE);
    let o = td(&["check", f.to_str().unwrap()]);
    assert_eq!(o.status.code(), Some(0), "{}", stderr(&o));
    assert_eq!(
        stdout(&o),
        format!(
            "{}: ok, 5 players, 3 of 4 rounds; round 3: 2 games pending\n",
            f.display()
        )
    );
}

#[test]
fn check_names_the_line_of_a_problem() {
    let f = file("bad", &LEAGUE.replace("5 2 -+", "5 6 -+"));
    let o = td(&["check", f.to_str().unwrap()]);
    assert_eq!(o.status.code(), Some(1));
    assert_eq!(stdout(&o), "");
    assert_eq!(
        stderr(&o),
        format!("td: {}: line 18: unknown player 6\n", f.display())
    );
}

#[test]
fn check_of_a_missing_file() {
    let o = td(&["check", "/nonexistent/league.trn"]);
    assert_eq!(o.status.code(), Some(1));
    assert!(
        stderr(&o).starts_with("td: /nonexistent/league.trn: "),
        "{}",
        stderr(&o)
    );
}

#[test]
fn players_by_start_number() {
    let f = file("players", LEAGUE);
    let o = td(&["players", f.to_str().unwrap()]);
    assert_eq!(o.status.code(), Some(0), "{}", stderr(&o));
    assert_eq!(
        stdout(&o),
        "\
No  Name            Rating
 1  Lindqvist, Mia    2105
 2  Okafor, Chidi     1987
 3  Šimić, Luka       1862
 4  Price, Nora          -
 5  Haddad, Rami      1650
"
    );
}

#[test]
fn players_by_rating_and_by_name() {
    let f = file("players-by", LEAGUE);
    let o = td(&["players", "--by", "rating", f.to_str().unwrap()]);
    let order: Vec<String> = stdout(&o)
        .lines()
        .skip(1)
        .map(|l| l.split_whitespace().next().unwrap().to_string())
        .collect();
    assert_eq!(order, ["1", "2", "3", "5", "4"]);
    let o = td(&["players", f.to_str().unwrap(), "--by", "name"]);
    let order: Vec<String> = stdout(&o)
        .lines()
        .skip(1)
        .map(|l| l.split_whitespace().next().unwrap().to_string())
        .collect();
    assert_eq!(order, ["5", "1", "2", "4", "3"]);
}

#[test]
fn card_lists_a_players_rounds() {
    let f = file("card", LEAGUE);
    let o = td(&["card", f.to_str().unwrap(), "2"]);
    assert_eq!(o.status.code(), Some(0), "{}", stderr(&o));
    assert_eq!(
        stdout(&o),
        "\
2 Okafor, Chidi (1987)

Round  Colour  Opponent          Result
    1  white   4 Price, Nora     1/2
    2  black   5 Haddad, Rami    -+
    3  black   1 Lindqvist, Mia  not played yet
"
    );
    let o = td(&["card", f.to_str().unwrap(), "3"]);
    assert!(
        stdout(&o).contains("    2  -       bye               half\n"),
        "{}",
        stdout(&o)
    );
}

#[test]
fn card_of_an_unknown_player() {
    let f = file("card-unknown", LEAGUE);
    let o = td(&["card", f.to_str().unwrap(), "9"]);
    assert_eq!(o.status.code(), Some(1));
    assert_eq!(stderr(&o), format!("td: {}: no player 9\n", f.display()));
}

#[test]
fn usage_errors_exit_2() {
    let f = file("usage", LEAGUE);
    let path = f.to_str().unwrap();
    for args in [
        vec![],
        vec!["dance"],
        vec!["check"],
        vec!["check", path, path],
        vec!["check", "--fast", path],
        vec!["players", "--by", "age", path],
        vec!["players", path, "--by"],
        vec!["players", "--by", "no", "--by", "name", path],
        vec!["card", path],
        vec!["card", path, "two"],
    ] {
        let o = td(&args);
        assert_eq!(o.status.code(), Some(2), "{args:?}");
        assert_eq!(stdout(&o), "", "{args:?}");
        assert!(stderr(&o).contains("usage: td"), "{args:?}: {}", stderr(&o));
    }
}
