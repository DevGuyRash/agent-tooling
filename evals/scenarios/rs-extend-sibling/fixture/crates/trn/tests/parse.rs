use trn::{parse, ByeKind, GameResult};

const SMALL: &str = "\
# Test file
event Club Night
rounds 3

player 1 1900 Able, Ann
player 2 1800 Baker, Bo
player 3 0    Cole,   Cy

round 1
1 2 1-0
bye 3 full

round 2
3 1 *
bye 2 half
";

#[test]
fn parses_header_players_and_rounds() {
    let t = parse(SMALL).unwrap();
    assert_eq!(t.event, "Club Night");
    assert_eq!(t.planned_rounds, 3);
    assert_eq!(t.players.len(), 3);
    assert_eq!(t.player(3).unwrap().name, "Cole, Cy");
    assert_eq!(t.player(3).unwrap().rating, 0);
    assert_eq!(t.rounds.len(), 2);
    let r1 = t.round(1).unwrap();
    assert_eq!(r1.games[0].white, 1);
    assert_eq!(r1.games[0].black, 2);
    assert_eq!(r1.games[0].result, GameResult::WhiteWins);
    assert_eq!(r1.byes[0].player, 3);
    assert_eq!(r1.byes[0].kind, ByeKind::Full);
    assert!(t.round(3).is_none());
}

#[test]
fn pending_games_leave_a_round_unfinished() {
    let t = parse(SMALL).unwrap();
    assert!(t.round(1).unwrap().is_finished());
    assert_eq!(t.round(2).unwrap().pending_games(), 1);
    assert!(!t.round(2).unwrap().is_finished());
}

#[test]
fn every_result_token() {
    for (token, result) in [
        ("1-0", GameResult::WhiteWins),
        ("0-1", GameResult::BlackWins),
        ("1/2", GameResult::Draw),
        ("+-", GameResult::WhiteForfeitWin),
        ("-+", GameResult::BlackForfeitWin),
        ("--", GameResult::DoubleForfeit),
        ("*", GameResult::Pending),
    ] {
        assert_eq!(GameResult::parse(token), Some(result));
        assert_eq!(result.token(), token);
    }
    assert_eq!(GameResult::parse("2-0"), None);
}

#[test]
fn crlf_and_indentation() {
    let text = SMALL
        .replace('\n', "\r\n")
        .replace("round 2", "   round 2  ");
    let t = parse(&text).unwrap();
    assert_eq!(t.event, "Club Night");
    assert_eq!(t.rounds.len(), 2);
}

fn error(text: &str) -> String {
    parse(text).unwrap_err().to_string()
}

#[test]
fn reports_problems_with_line_numbers() {
    assert_eq!(
        error(&SMALL.replace("1 2 1-0", "1 4 1-0")),
        "line 10: unknown player 4"
    );
    assert_eq!(
        error(&SMALL.replace("1 2 1-0", "1 2 2-0")),
        "line 10: unknown result \"2-0\""
    );
    assert_eq!(
        error(&SMALL.replace("bye 2 half", "bye 2 double")),
        "line 15: unknown bye \"double\" (full, half, or zero)"
    );
    assert_eq!(
        error(&SMALL.replace("bye 3 full", "bye 1 full")),
        "line 11: player 1 appears twice in round 1"
    );
    assert_eq!(
        error(&SMALL.replace("bye 3 full", "")),
        "line 9: player 3 is missing from round 1"
    );
    assert_eq!(
        error(&SMALL.replace("round 2", "round 3")),
        "line 13: expected round 2, found round 3"
    );
    assert_eq!(
        error(&SMALL.replace("rounds 3", "rounds 1")),
        "line 13: round 2 exceeds the 1 planned rounds"
    );
    assert_eq!(
        error(&SMALL.replace("1 2 1-0", "2 2 1-0")),
        "line 10: player 2 cannot play itself"
    );
    assert_eq!(
        error(&SMALL.replace("1900", "99")),
        "line 5: rating 99 is out of range (0 for unrated, or 100 to 3000)"
    );
    assert_eq!(
        error(&SMALL.replace("player 2 1800", "player 1 1800")),
        "line 6: player 1 declared twice"
    );
    assert_eq!(
        error(&format!("{SMALL}player 4 1500 Late, Lou\n")),
        "line 16: players must come before round 1"
    );
    assert_eq!(
        error(&SMALL.replace("round 1", "rnd 1")),
        "line 9: unknown statement \"rnd\""
    );
    assert_eq!(
        error(&SMALL.replace("event Club Night\n", "")),
        "line 8: event and rounds must come before round 1"
    );
}

#[test]
fn missing_statements() {
    assert_eq!(error("rounds 2\nplayer 1 0 A\n"), "missing event line");
    assert_eq!(error("event E\nplayer 1 0 A\n"), "missing rounds line");
    assert_eq!(error("event E\nrounds 2\n"), "no players");
    assert_eq!(error("event E\nevent F\n"), "line 2: event given twice");
}
