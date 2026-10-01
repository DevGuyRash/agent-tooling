//! Plain-text tables for td's output.
//!
//! Columns are separated by two spaces, and each column is as wide as its widest cell, header included,
//! counting characters (not bytes), so names such as "Šimić" line up. Cells are padded according to their
//! column's alignment, and no line ends in spaces.

/// How a column's cells (and its header) are padded.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Align {
    Left,
    Right,
}

#[derive(Debug, Clone)]
pub struct Table {
    aligns: Vec<Align>,
    rows: Vec<Vec<String>>,
}

impl Table {
    /// A table with one column per header entry.
    pub fn new(header: &[(&str, Align)]) -> Table {
        Table {
            aligns: header.iter().map(|(_, a)| *a).collect(),
            rows: vec![header.iter().map(|(h, _)| h.to_string()).collect()],
        }
    }

    /// Add a row. Panics when the row has a different number of cells than the header.
    pub fn row<S: Into<String>>(&mut self, cells: Vec<S>) {
        let cells: Vec<String> = cells.into_iter().map(Into::into).collect();
        assert_eq!(
            cells.len(),
            self.aligns.len(),
            "row has {} cells, table has {} columns",
            cells.len(),
            self.aligns.len()
        );
        self.rows.push(cells);
    }

    /// Number of rows, header included.
    pub fn len(&self) -> usize {
        self.rows.len()
    }

    pub fn is_empty(&self) -> bool {
        self.rows.is_empty()
    }

    /// The table as lines, each ending in a newline.
    pub fn render(&self) -> String {
        let widths: Vec<usize> = (0..self.aligns.len())
            .map(|c| {
                self.rows
                    .iter()
                    .map(|r| r[c].chars().count())
                    .max()
                    .unwrap_or(0)
            })
            .collect();
        let mut out = String::new();
        for row in &self.rows {
            let mut line = String::new();
            for (c, cell) in row.iter().enumerate() {
                if c > 0 {
                    line.push_str("  ");
                }
                let pad = widths[c] - cell.chars().count();
                match self.aligns[c] {
                    Align::Left => {
                        line.push_str(cell);
                        line.extend(std::iter::repeat_n(' ', pad));
                    }
                    Align::Right => {
                        line.extend(std::iter::repeat_n(' ', pad));
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
