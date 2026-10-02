//! Plain-text tables for pagerlog's reports.
//!
//! Columns are separated by two spaces and each is as wide as its widest cell, header included, counting
//! characters rather than bytes. Text columns are left-aligned and number columns right-aligned, headers
//! like their column, and no line ends in spaces.

/// How a column's cells, and its header, are padded.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Align {
    Left,
    Right,
}

/// A table being filled in, row by row.
#[derive(Debug, Clone)]
pub struct Table {
    aligns: Vec<Align>,
    rows: Vec<Vec<String>>,
}

impl Table {
    /// A table with one column per header entry.
    pub fn new(columns: &[(&str, Align)]) -> Table {
        Table {
            aligns: columns.iter().map(|&(_, a)| a).collect(),
            rows: vec![columns.iter().map(|&(h, _)| h.to_string()).collect()],
        }
    }

    /// Add a row. Panics when it does not have one cell per column.
    pub fn push<S: Into<String>>(&mut self, cells: Vec<S>) {
        let cells: Vec<String> = cells.into_iter().map(Into::into).collect();
        assert_eq!(cells.len(), self.aligns.len(), "a row needs one cell per column");
        self.rows.push(cells);
    }

    /// Rows added so far, the header not counted.
    pub fn len(&self) -> usize {
        self.rows.len() - 1
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// The table as text, every line ending in a newline.
    pub fn render(&self) -> String {
        let mut widths = vec![0; self.aligns.len()];
        for row in &self.rows {
            for (w, cell) in widths.iter_mut().zip(row) {
                *w = (*w).max(cell.chars().count());
            }
        }
        let mut out = String::new();
        for row in &self.rows {
            let mut line = String::new();
            for (c, cell) in row.iter().enumerate() {
                if c > 0 {
                    line.push_str("  ");
                }
                let pad = " ".repeat(widths[c] - cell.chars().count());
                match self.aligns[c] {
                    Align::Left => {
                        line.push_str(cell);
                        line.push_str(&pad);
                    }
                    Align::Right => {
                        line.push_str(&pad);
                        line.push_str(cell);
                    }
                }
            }
            out.push_str(line.trim_end_matches(' '));
            out.push('\n');
        }
        out
    }
}
