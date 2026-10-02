use race::{duration, layout, parse, Clock, Finish};

const EXAMPLE: &str = "\
# Autumn Series, race 1
race Autumn Series 1
start 14:00:00
boat 207101 | Ann Hale    | ILCA 7   | 15:02:37
boat 1432   | Raj Patel   | Topper   | 15:10:04
boat 2210   | Lee Wong    | Optimist | DNF
boat 3301   | Sam Ito     | Wayfarer | DNS

boat 4000   | Jo Park     | Solo
";

#[test]
fn parses_the_documented_example() {
    let race = parse(EXAMPLE).unwrap();
    assert_eq!(race.name, "Autumn Series 1");
    assert_eq!(race.start, Clock::parse("14:00:00").unwrap());
    assert_eq!(race.boats.len(), 5);
    let ann = &race.boats[0];
    assert_eq!((ann.line, ann.sail.as_str(), ann.helm.as_str(), ann.class.as_str()), (4, "207101", "Ann Hale", "ILCA 7"));
    assert_eq!(ann.finish, Finish::Time(Clock::from_seconds(15 * 3600 + 2 * 60 + 37)));
    assert_eq!(race.boats[2].finish, Finish::Dnf);
    assert_eq!(race.boats[3].finish, Finish::Dns);
    assert_eq!(race.boats[4].finish, Finish::NotYet);
}

#[test]
fn accepts_crlf_and_an_empty_finish() {
    let race = parse("race R\r\nstart 09:00:00\r\nboat 1 | A | Solo | \r\n").unwrap();
    assert_eq!(race.boats[0].finish, Finish::NotYet);
    assert_eq!(race.boats[0].class, "Solo");
}

#[test]
fn errors_name_the_line() {
    let cases = [
        ("race R\nstart 14:00:00\nboat 1 | A | Solo | 15:7:00\n", "line 3: bad finish \"15:7:00\""),
        ("race R\nstart 14:00:00\nfinish 1\n", "line 3: unknown line \"finish\""),
        ("race R\nstart 14:00:00\nboat 1 | A | Solo\nboat 1 | B | Solo\n", "line 4: sail 1 is already entered on line 3"),
        ("race R\nboat 1 | A | Solo\n", "no start line"),
        ("start 14:00:00\n", "no race line"),
        ("race R\nstart 14:00:00\nboat 1 | A | Solo | 13:59:59\n", "line 3: finish 13:59:59 is not after the start 14:00:00"),
        ("race R\nstart 14:00:00\nboat 12a | A | Solo\n", "line 3: bad sail number \"12a\""),
        ("race R\nstart 14:00:00\nboat 1 | A\n", "line 3: a boat line is: boat SAIL | HELM | CLASS [| FINISH]"),
        ("race R\nstart 2pm\n", "line 2: bad start time \"2pm\""),
    ];
    for (text, message) in cases {
        assert_eq!(parse(text).unwrap_err().to_string(), message, "{text:?}");
    }
}

#[test]
fn clock_times() {
    let t = Clock::parse("09:05:07").unwrap();
    assert_eq!(t.seconds(), 9 * 3600 + 5 * 60 + 7);
    assert_eq!(t.to_string(), "09:05:07");
    assert_eq!(t.plus(3600).unwrap().to_string(), "10:05:07");
    assert_eq!(Clock::parse("23:59:59").unwrap().plus(1), None);
    assert_eq!(Clock::parse("00:04:00").unwrap().minus(300), None);
    for bad in ["9:05:07", "24:00:00", "12:60:00", "12-00-00", "12:00:0x", ""] {
        assert_eq!(Clock::parse(bad), None, "{bad}");
    }
    assert_eq!(duration(3082), "0:51:22");
    assert_eq!(duration(4204), "1:10:04");
}

#[test]
fn layout_aligns_columns() {
    let rows = vec![
        vec!["a".to_string(), "num".to_string(), "".to_string()],
        vec!["longer".to_string(), "7".to_string(), "".to_string()],
        vec!["Thé".to_string(), "1234".to_string(), "x".to_string()],
    ];
    assert_eq!(layout(&rows, &[false, true, false]), "a        num\nlonger     7\nThé     1234  x\n");
}
