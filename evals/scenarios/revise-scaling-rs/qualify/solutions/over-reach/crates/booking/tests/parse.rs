use booking::{parse_export, Date, Status, HEADER};

fn export(lines: &[&str]) -> String {
    let mut text = format!("{HEADER}\n");
    for l in lines {
        text.push_str(l);
        text.push('\n');
    }
    text
}

#[test]
fn reads_bookings() {
    let bookings = parse_export(&export(&[
        "B26-0003101,KGS-SQ1,2026-09-14,18:00,18:40,confirmed,M004512",
        "B26-0003150,kgs - sq3,2026-09-19,18:40,19:20,provisional,DESK-KGS",
        "B26-0003131,KGS-ST1,2026-09-17,19:30,20:30,cancelled,C0058",
    ]))
    .unwrap();
    assert_eq!(bookings.len(), 3);
    assert_eq!(bookings[0].reference, "B26-0003101");
    assert_eq!(
        bookings[0].date,
        Date {
            year: 2026,
            month: 9,
            day: 14
        }
    );
    assert_eq!(
        (bookings[0].start, bookings[0].end),
        (18 * 60, 18 * 60 + 40)
    );
    assert_eq!(bookings[1].facility, "kgs - sq3");
    assert_eq!(bookings[1].line, 3);
    assert_eq!(bookings[1].status, Status::Provisional);
    assert_eq!(bookings[2].status, Status::Cancelled);
}

#[test]
fn accepts_windows_line_endings_and_blank_lines() {
    let text =
        format!("{HEADER}\r\nB26-0003101,KGS-SQ1,2026-09-14,18:00,18:40,confirmed,M004512\r\n\r\n");
    assert_eq!(parse_export(&text).unwrap().len(), 1);
}

#[test]
fn reports_every_problem_with_its_line() {
    let problems = parse_export(&export(&[
        "B26-0003101,KGS-SQ1,2026-09-14,18:00,18:40,confirmed,M004512",
        "B26-0003102,KGS-SQ1,2026-02-29,18:40,19:20,confirmed,M001877",
        "B26-0003105,KGS-SQ2,2026-09-14,18:00,24:00,confirmed,M002210",
        "B26-0003106,KGS-SQ2,2026-09-14,18:40,18:40,confirmed,M002210",
        "B26 0003107,KGS-SQ2,2026-09-14,19:20,20:00,confirmed,M002210",
        "B26-0003108,KGS-SQ2,2026-09-14,19:20,20:00,held,M002210",
    ]))
    .unwrap_err();
    let shown: Vec<String> = problems.iter().map(|p| p.to_string()).collect();
    assert_eq!(
        shown,
        [
            "line 3: invalid date: 2026-02-29",
            "line 4: invalid time: 24:00",
            "line 5: ends at 18:40, not after it starts at 18:40",
            "line 6: bad booking reference 'B26 0003107'",
            "line 7: invalid status: held",
        ]
    );
}

#[test]
fn a_reference_given_twice_is_a_problem_naming_the_first_line() {
    let problems = parse_export(&export(&[
        "B26-0003101,KGS-SQ1,2026-09-14,18:00,18:40,confirmed,M004512",
        "B26-0003102,KGS-SQ1,2026-09-14,18:40,19:20,confirmed,M001877",
        "B26-0003101,KGS-SQ3,2026-09-19,18:20,19:00,confirmed,M004512",
    ]))
    .unwrap_err();
    assert_eq!(problems.len(), 1);
    assert_eq!(
        problems[0].to_string(),
        "line 4: booking B26-0003101 is already on line 2"
    );
}

#[test]
fn refuses_a_file_without_the_header() {
    let problems =
        parse_export("B26-0003101,KGS-SQ1,2026-09-14,18:00,18:40,confirmed,M004512\n").unwrap_err();
    assert_eq!(
        problems[0].to_string(),
        format!("line 1: expected the header {HEADER}")
    );
}

#[test]
fn facility_codes_agree_ignoring_case_and_spaces() {
    assert!(booking::same_facility("KGS-SQ3", "kgs - sq3"));
    assert!(!booking::same_facility("KGS-SQ3", "KGS-SQ30"));
    assert_eq!(booking::normalize_facility(" rvp-Pool-L4 "), "RVP-POOL-L4");
    assert_eq!(booking::centre("RVP-POOL-L4"), "RVP");
}
