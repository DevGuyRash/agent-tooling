//! Reading history exports.

use history::{parse, Error, Time};

const EXPORT: &str = "time\talert\treceivers\tlabels
2026-07-01T03:12:44Z\tDiskFull\tstorage-oncall\tservice=db-orders,severity=critical,team=storage
2026-07-01T03:14:02Z\tApiLatency\tpayments-oncall,payments-tickets\tenv=prod,service=checkout,team=payments

2026-06-30T23:59:59Z\tCertExpiry\tplatform-tickets\t-
";

fn error(text: &str) -> String {
    parse(text).unwrap_err().to_string()
}

fn with_line(line: &str) -> String {
    format!("{}\n{line}\n", history::HEADER)
}

#[test]
fn reads_every_alert_in_file_order() {
    let h = parse(EXPORT).unwrap();
    assert_eq!(h.alerts.len(), 3);
    let a = &h.alerts[1];
    assert_eq!(a.line, 3);
    assert_eq!(a.name, "ApiLatency");
    assert_eq!(a.receivers, ["payments-oncall", "payments-tickets"]);
    assert_eq!(a.label("service"), Some("checkout"));
    assert_eq!(a.label("region"), None);
    assert_eq!(h.alerts[2].line, 5);
    assert!(h.alerts[2].labels.is_empty());
}

#[test]
fn first_and_last_are_by_time_not_by_line() {
    let h = parse(EXPORT).unwrap();
    assert_eq!(h.first().unwrap().to_string(), "2026-06-30T23:59:59Z");
    assert_eq!(h.last().unwrap().to_string(), "2026-07-01T03:14:02Z");
    assert_eq!(parse(history::HEADER).unwrap().first(), None);
}

#[test]
fn crlf_line_endings() {
    let h = parse(&EXPORT.replace('\n', "\r\n")).unwrap();
    assert_eq!(h.alerts.len(), 3);
    assert_eq!(h.alerts[2].receivers, ["platform-tickets"]);
}

#[test]
fn times() {
    let t = Time::parse("2026-10-03T02:15:09Z").unwrap();
    assert_eq!((t.year, t.month, t.day, t.hour, t.minute, t.second), (2026, 10, 3, 2, 15, 9));
    assert_eq!(t.weekday(), 5); // a Saturday
    assert_eq!(t.minute_of_day(), 135);
    assert_eq!(t.date(), "2026-10-03");
    assert_eq!(Time::parse("1970-01-01T00:00:00Z").unwrap().weekday(), 3);
    assert_eq!(Time::parse("2000-02-29T12:00:00Z").unwrap().weekday(), 1);
    assert_eq!(Time::parse("2024-12-30T00:00:00Z").unwrap().days_since_epoch(), 20087);
    for bad in [
        "2026-02-29T00:00:00Z",
        "2026-13-01T00:00:00Z",
        "2026-04-31T00:00:00Z",
        "2026-07-01T24:00:00Z",
        "2026-07-01T23:60:00Z",
        "2026-07-01T23:59:60Z",
        "2026-07-01 03:12:44Z",
        "2026-07-01T03:12:44",
        "2026-07-01T03:12:44+00:00",
        "2026-7-01T03:12:44Z",
    ] {
        assert_eq!(Time::parse(bad), None, "{bad}");
    }
    assert!(Time::parse("2024-02-29T00:00:00Z").is_some());
    assert!(Time::parse("2026-07-01T03:12:44Z") < Time::parse("2026-07-01T03:12:45Z"));
}

#[test]
fn header() {
    assert_eq!(error(""), "line 1: bad header");
    assert_eq!(error("time\talert\treceivers\n"), "line 1: bad header");
    assert_eq!(
        parse(&EXPORT[EXPORT.find('\n').unwrap() + 1..]).unwrap_err(),
        Error { line: 1, message: "bad header".to_string() }
    );
}

#[test]
fn field_errors() {
    let cases = [
        ("2026-07-01T03:12:44Z\tDiskFull\tstorage-oncall", "expected 4 fields, found 3"),
        ("2026-07-01T03:12:44Z\tDiskFull\tstorage-oncall\t-\textra", "expected 4 fields, found 5"),
        ("2026-07-01T03:12:44\tDiskFull\tstorage-oncall\t-", "bad time \"2026-07-01T03:12:44\""),
        ("2026-07-01T03:12:44Z\tDisk Full\tstorage-oncall\t-", "bad alert name \"Disk Full\""),
        ("2026-07-01T03:12:44Z\t\tstorage-oncall\t-", "bad alert name \"\""),
        ("2026-07-01T03:12:44Z\tDiskFull\tStorage\t-", "bad receivers \"Storage\""),
        ("2026-07-01T03:12:44Z\tDiskFull\ta,,b\t-", "bad receivers \"a,,b\""),
        ("2026-07-01T03:12:44Z\tDiskFull\ta,b,a\t-", "bad receivers \"a,b,a\""),
        ("2026-07-01T03:12:44Z\tDiskFull\ta\tteam", "bad label \"team\""),
        ("2026-07-01T03:12:44Z\tDiskFull\ta\tteam=", "bad label \"team=\""),
        ("2026-07-01T03:12:44Z\tDiskFull\ta\tTeam=x", "bad label \"Team=x\""),
        ("2026-07-01T03:12:44Z\tDiskFull\ta\tteam=a b", "bad label \"team=a b\""),
        ("2026-07-01T03:12:44Z\tDiskFull\ta\tteam=x,team=y", "label \"team\" given twice"),
        ("2026-07-01T03:12:44Z\tDiskFull\ta\talertname=X", "label \"alertname\" is reserved"),
    ];
    for (line, message) in cases {
        assert_eq!(error(&with_line(line)), format!("line 2: {message}"), "{line}");
    }
}

#[test]
fn values_may_hold_equals_signs() {
    let h = parse(&with_line("2026-07-01T03:12:44Z\tDiskFull\ta\tquery=a=b")).unwrap();
    assert_eq!(h.alerts[0].label("query"), Some("a=b"));
}
