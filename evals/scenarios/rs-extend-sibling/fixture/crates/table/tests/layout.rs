use table::{Align, Table};

#[test]
fn columns_are_as_wide_as_their_widest_cell() {
    let mut t = Table::new(&[
        ("No", Align::Right),
        ("Name", Align::Left),
        ("Rating", Align::Right),
    ]);
    t.row(vec!["1", "Lindqvist, Mia", "2105"]);
    t.row(vec!["12", "Li, Bo", "-"]);
    assert_eq!(
        t.render(),
        "No  Name            Rating\n 1  Lindqvist, Mia    2105\n12  Li, Bo               -\n"
    );
}

#[test]
fn widths_count_characters_not_bytes() {
    let mut t = Table::new(&[("Name", Align::Left), ("Pts", Align::Right)]);
    t.row(vec!["Šimić, Luka", "3"]);
    t.row(vec!["Cole, Cy", "2.5"]);
    assert_eq!(
        t.render(),
        "Name         Pts\nŠimić, Luka    3\nCole, Cy     2.5\n"
    );
}

#[test]
fn no_line_ends_in_spaces() {
    let mut t = Table::new(&[("No", Align::Right), ("Name", Align::Left)]);
    t.row(vec!["1", "A much longer name"]);
    t.row(vec!["2", "Short"]);
    for line in t.render().lines() {
        assert!(!line.ends_with(' '), "{line:?}");
    }
    assert!(t.render().ends_with("2  Short\n"));
}

#[test]
fn header_only() {
    let t = Table::new(&[("A", Align::Left), ("B", Align::Right)]);
    assert_eq!(t.len(), 1);
    assert_eq!(t.render(), "A  B\n");
}

#[test]
#[should_panic]
fn rows_must_match_the_header() {
    let mut t = Table::new(&[("A", Align::Left), ("B", Align::Right)]);
    t.row(vec!["only one"]);
}
