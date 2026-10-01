//! Parse and validate Rookhaven tournament files (`.trn`). The format is described in docs/format.md.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

/// A whole tournament file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Tournament {
    pub event: String,
    /// Number of rounds planned (`rounds N`).
    pub planned_rounds: u32,
    /// Players in the order the file declares them.
    pub players: Vec<Player>,
    /// Rounds 1, 2, 3, ... as far as the file goes.
    pub rounds: Vec<Round>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Player {
    /// Start number.
    pub no: u32,
    /// 0 for unrated.
    pub rating: u32,
    pub name: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Round {
    pub number: u32,
    pub games: Vec<Game>,
    pub byes: Vec<Bye>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Game {
    pub white: u32,
    pub black: u32,
    pub result: GameResult,
    /// Line in the file, for messages.
    pub line: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GameResult {
    /// `1-0`
    WhiteWins,
    /// `0-1`
    BlackWins,
    /// `1/2`
    Draw,
    /// `+-`: White won by forfeit; Black did not play.
    WhiteForfeitWin,
    /// `-+`: Black won by forfeit; White did not play.
    BlackForfeitWin,
    /// `--`: neither player played.
    DoubleForfeit,
    /// `*`: not played yet.
    Pending,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Bye {
    pub player: u32,
    pub kind: ByeKind,
    pub line: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ByeKind {
    /// `full`: one point.
    Full,
    /// `half`: half a point.
    Half,
    /// `zero`: no points (absences and withdrawals too).
    Zero,
}

/// What went wrong, and on which line (None when the problem is a missing statement).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParseError {
    pub line: Option<usize>,
    pub message: String,
}

impl fmt::Display for ParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self.line {
            Some(n) => write!(f, "line {n}: {}", self.message),
            None => f.write_str(&self.message),
        }
    }
}

impl std::error::Error for ParseError {}

impl GameResult {
    pub fn parse(token: &str) -> Option<GameResult> {
        Some(match token {
            "1-0" => GameResult::WhiteWins,
            "0-1" => GameResult::BlackWins,
            "1/2" => GameResult::Draw,
            "+-" => GameResult::WhiteForfeitWin,
            "-+" => GameResult::BlackForfeitWin,
            "--" => GameResult::DoubleForfeit,
            "*" => GameResult::Pending,
            _ => return None,
        })
    }

    /// The token as it is written in a file.
    pub fn token(self) -> &'static str {
        match self {
            GameResult::WhiteWins => "1-0",
            GameResult::BlackWins => "0-1",
            GameResult::Draw => "1/2",
            GameResult::WhiteForfeitWin => "+-",
            GameResult::BlackForfeitWin => "-+",
            GameResult::DoubleForfeit => "--",
            GameResult::Pending => "*",
        }
    }
}

impl ByeKind {
    pub fn parse(token: &str) -> Option<ByeKind> {
        match token {
            "full" => Some(ByeKind::Full),
            "half" => Some(ByeKind::Half),
            "zero" => Some(ByeKind::Zero),
            _ => None,
        }
    }

    pub fn token(self) -> &'static str {
        match self {
            ByeKind::Full => "full",
            ByeKind::Half => "half",
            ByeKind::Zero => "zero",
        }
    }
}

impl Tournament {
    /// The player with start number `no`.
    pub fn player(&self, no: u32) -> Option<&Player> {
        self.players.iter().find(|p| p.no == no)
    }

    /// Round `number` (1-based), if the file has it.
    pub fn round(&self, number: u32) -> Option<&Round> {
        self.rounds.get(number.checked_sub(1)? as usize)
    }
}

impl Round {
    /// Games in this round still to be played (`*`).
    pub fn pending_games(&self) -> usize {
        self.games
            .iter()
            .filter(|g| g.result == GameResult::Pending)
            .count()
    }

    /// A round is finished when none of its games is pending.
    pub fn is_finished(&self) -> bool {
        self.pending_games() == 0
    }
}

fn err<T>(line: usize, message: impl Into<String>) -> Result<T, ParseError> {
    Err(ParseError {
        line: Some(line),
        message: message.into(),
    })
}

fn number(line: usize, what: &str, token: &str) -> Result<u32, ParseError> {
    match token.parse::<u32>() {
        Ok(n) if token.bytes().all(|b| b.is_ascii_digit()) => Ok(n),
        _ => err(
            line,
            format!("{what} must be a whole number, not \"{token}\""),
        ),
    }
}

struct Open {
    round: Round,
    line: usize,
    seen: BTreeSet<u32>,
}

/// Parse a tournament file and check it against the rules in docs/format.md.
pub fn parse(text: &str) -> Result<Tournament, ParseError> {
    let mut event: Option<String> = None;
    let mut planned: Option<u32> = None;
    let mut players: Vec<Player> = Vec::new();
    let mut known: BTreeMap<u32, usize> = BTreeMap::new();
    let mut rounds: Vec<Round> = Vec::new();
    let mut open: Option<Open> = None;

    for (i, raw) in text.lines().enumerate() {
        let n = i + 1;
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let fields: Vec<&str> = line.split_whitespace().collect();
        match fields[0] {
            "event" => {
                if event.is_some() {
                    return err(n, "event given twice");
                }
                let name = line["event".len()..].trim();
                if name.is_empty() {
                    return err(n, "event needs a name");
                }
                event = Some(name.to_string());
            }
            "rounds" => {
                if planned.is_some() {
                    return err(n, "rounds given twice");
                }
                if fields.len() != 2 {
                    return err(n, "usage: rounds N");
                }
                let count = number(n, "the number of rounds", fields[1])?;
                if count == 0 {
                    return err(n, "a tournament needs at least one round");
                }
                planned = Some(count);
            }
            "player" => {
                if open.is_some() || !rounds.is_empty() {
                    return err(n, "players must come before round 1");
                }
                if fields.len() < 4 {
                    return err(n, "usage: player NO RATING NAME");
                }
                let no = number(n, "a start number", fields[1])?;
                if no == 0 {
                    return err(n, "start numbers begin at 1");
                }
                let rating = number(n, "a rating", fields[2])?;
                if rating != 0 && !(100..=3000).contains(&rating) {
                    return err(
                        n,
                        format!("rating {rating} is out of range (0 for unrated, or 100 to 3000)"),
                    );
                }
                if known.contains_key(&no) {
                    return err(n, format!("player {no} declared twice"));
                }
                let name = fields[3..].join(" ");
                known.insert(no, players.len());
                players.push(Player { no, rating, name });
            }
            "round" => {
                let (Some(_), Some(planned)) = (&event, planned) else {
                    return err(n, "event and rounds must come before round 1");
                };
                if players.is_empty() {
                    return err(n, "no players before round 1");
                }
                if fields.len() != 2 {
                    return err(n, "usage: round N");
                }
                let number_given = number(n, "a round number", fields[1])?;
                if let Some(o) = open.take() {
                    rounds.push(close(o, &known)?);
                }
                let expected = rounds.len() as u32 + 1;
                if number_given != expected {
                    return err(
                        n,
                        format!("expected round {expected}, found round {number_given}"),
                    );
                }
                if number_given > planned {
                    return err(
                        n,
                        format!("round {number_given} exceeds the {planned} planned rounds"),
                    );
                }
                open = Some(Open {
                    round: Round {
                        number: number_given,
                        games: Vec::new(),
                        byes: Vec::new(),
                    },
                    line: n,
                    seen: BTreeSet::new(),
                });
            }
            "bye" => {
                let Some(o) = open.as_mut() else {
                    return err(n, "bye before round 1");
                };
                if fields.len() != 3 {
                    return err(n, "usage: bye NO full|half|zero");
                }
                let no = number(n, "a start number", fields[1])?;
                let Some(kind) = ByeKind::parse(fields[2]) else {
                    return err(
                        n,
                        format!("unknown bye \"{}\" (full, half, or zero)", fields[2]),
                    );
                };
                pair_once(o, &known, no, n)?;
                o.round.byes.push(Bye {
                    player: no,
                    kind,
                    line: n,
                });
            }
            first if first.bytes().all(|b| b.is_ascii_digit()) => {
                let Some(o) = open.as_mut() else {
                    return err(n, "game before round 1");
                };
                if fields.len() != 3 {
                    return err(n, "usage: WHITE BLACK RESULT");
                }
                let white = number(n, "a start number", fields[0])?;
                let black = number(n, "a start number", fields[1])?;
                let Some(result) = GameResult::parse(fields[2]) else {
                    return err(n, format!("unknown result \"{}\"", fields[2]));
                };
                if white == black {
                    return err(n, format!("player {white} cannot play itself"));
                }
                pair_once(o, &known, white, n)?;
                pair_once(o, &known, black, n)?;
                o.round.games.push(Game {
                    white,
                    black,
                    result,
                    line: n,
                });
            }
            other => return err(n, format!("unknown statement \"{other}\"")),
        }
    }
    if let Some(o) = open.take() {
        rounds.push(close(o, &known)?);
    }
    let Some(event) = event else {
        return Err(ParseError {
            line: None,
            message: "missing event line".into(),
        });
    };
    let Some(planned_rounds) = planned else {
        return Err(ParseError {
            line: None,
            message: "missing rounds line".into(),
        });
    };
    if players.is_empty() {
        return Err(ParseError {
            line: None,
            message: "no players".into(),
        });
    }
    Ok(Tournament {
        event,
        planned_rounds,
        players,
        rounds,
    })
}

fn pair_once(
    o: &mut Open,
    known: &BTreeMap<u32, usize>,
    no: u32,
    line: usize,
) -> Result<(), ParseError> {
    if !known.contains_key(&no) {
        return err(line, format!("unknown player {no}"));
    }
    if !o.seen.insert(no) {
        return err(
            line,
            format!("player {no} appears twice in round {}", o.round.number),
        );
    }
    Ok(())
}

fn close(o: Open, known: &BTreeMap<u32, usize>) -> Result<Round, ParseError> {
    if let Some(missing) = known.keys().find(|no| !o.seen.contains(no)) {
        return err(
            o.line,
            format!("player {missing} is missing from round {}", o.round.number),
        );
    }
    Ok(o.round)
}
