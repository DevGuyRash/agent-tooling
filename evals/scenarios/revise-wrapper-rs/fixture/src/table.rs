//! Plain-text tables: columns two spaces apart, each as wide as its widest cell in characters.

/// How a column's cells line up.
#[derive(Clone, Copy)]
pub enum Align {
    Left,
    Right,
}

/// The header and rows as lines (each ending in a newline); the last column is never padded.
pub fn render(header: &[&str], aligns: &[Align], rows: &[Vec<String>]) -> String {
    let mut widths: Vec<usize> = header.iter().map(|h| h.chars().count()).collect();
    for row in rows {
        for (w, cell) in widths.iter_mut().zip(row) {
            *w = (*w).max(cell.chars().count());
        }
    }
    let mut out = String::new();
    let header: Vec<String> = header.iter().map(|h| h.to_string()).collect();
    for row in std::iter::once(&header).chain(rows) {
        let last = row.len() - 1;
        let cells: Vec<String> = row
            .iter()
            .enumerate()
            .map(|(i, cell)| match (i == last, aligns[i]) {
                (true, _) => cell.clone(),
                (false, Align::Left) => format!("{cell:<w$}", w = widths[i]),
                (false, Align::Right) => format!("{cell:>w$}", w = widths[i]),
            })
            .collect();
        out.push_str(&cells.join("  "));
        out.push('\n');
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn widths_count_characters() {
        let rows = vec![vec!["frigo-entrée".to_string(), "4.1".to_string(), "ok".to_string()]];
        let text = render(&["unit", "temp", "status"], &[Align::Left, Align::Right, Align::Left], &rows);
        assert_eq!(text, "unit          temp  status\nfrigo-entrée   4.1  ok\n");
    }
}
