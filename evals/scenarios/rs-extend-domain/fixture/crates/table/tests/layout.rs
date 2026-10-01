//! How tables are laid out.

use table::{Align, Table};

#[test]
fn columns_are_as_wide_as_their_widest_cell() {
    let mut t = Table::new(&[("Receiver", Align::Left), ("Alerts", Align::Right)]);
    t.push(vec!["dba-oncall", "7"]);
    t.push(vec!["platform-oncall", "1204"]);
    assert_eq!(
        t.render(),
        "Receiver         Alerts\n\
         dba-oncall            7\n\
         platform-oncall    1204\n"
    );
}

#[test]
fn widths_count_characters_not_bytes() {
    let mut t = Table::new(&[("Site", Align::Left), ("N", Align::Right)]);
    t.push(vec!["Zürich", "3"]);
    t.push(vec!["Oslo", "12"]);
    assert_eq!(t.render(), "Site     N\nZürich   3\nOslo    12\n");
}

#[test]
fn no_line_ends_in_spaces() {
    let mut t = Table::new(&[("Alert", Align::Left), ("Receivers", Align::Left)]);
    t.push(vec!["DiskFull", ""]);
    t.push(vec!["X", "dba-oncall"]);
    for line in t.render().lines() {
        assert_eq!(line, line.trim_end(), "{line:?}");
    }
    assert_eq!(t.render(), "Alert     Receivers\nDiskFull\nX         dba-oncall\n");
}

#[test]
fn headers_align_like_their_column() {
    let mut t = Table::new(&[("N", Align::Right), ("Name", Align::Left)]);
    t.push(vec!["100", "a"]);
    assert_eq!(t.render(), "  N  Name\n100  a\n");
    assert_eq!(t.len(), 1);
    assert!(!t.is_empty());
}

#[test]
#[should_panic(expected = "one cell per column")]
fn a_row_needs_every_cell() {
    let mut t = Table::new(&[("A", Align::Left), ("B", Align::Left)]);
    t.push(vec!["only one"]);
}
