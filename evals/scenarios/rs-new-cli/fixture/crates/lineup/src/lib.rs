//! Align columns of text: the logic behind the `lineup` binary.

use std::collections::BTreeSet;

/// How to lay out the columns.
#[derive(Debug, Clone, Default)]
pub struct Layout {
    /// Columns (1-based) whose cells are right-aligned; the rest are left-aligned.
    pub right: BTreeSet<usize>,
    /// Split cells on this character instead of on runs of spaces and tabs.
    pub delimiter: Option<char>,
    /// Spaces between columns.
    pub gap: usize,
}

impl Layout {
    pub fn new() -> Layout {
        Layout { right: BTreeSet::new(), delimiter: None, gap: 2 }
    }
}

/// Parse a column list such as "2,4" into column numbers.
pub fn parse_columns(spec: &str) -> Result<BTreeSet<usize>, String> {
    spec.split(',')
        .map(|part| match part.trim().parse::<usize>() {
            Ok(n) if n >= 1 => Ok(n),
            _ => Err(format!("invalid column {part:?} (columns are numbered from 1)")),
        })
        .collect()
}

fn cells<'a>(line: &'a str, layout: &Layout) -> Vec<&'a str> {
    match layout.delimiter {
        Some(d) => line.split(d).map(str::trim).collect(),
        None => line.split([' ', '\t']).filter(|c| !c.is_empty()).collect(),
    }
}

/// Align `lines`. Blank lines stay blank, and lines starting with `#` pass through unchanged and do not
/// count towards column widths. Widths are measured in characters.
pub fn align(lines: &[&str], layout: &Layout) -> Vec<String> {
    let rows: Vec<Option<Vec<&str>>> = lines
        .iter()
        .map(|line| if line.trim().is_empty() || line.starts_with('#') { None } else { Some(cells(line, layout)) })
        .collect();
    let mut widths: Vec<usize> = Vec::new();
    for row in rows.iter().flatten() {
        for (i, cell) in row.iter().enumerate() {
            let w = cell.chars().count();
            if i == widths.len() {
                widths.push(w);
            } else if w > widths[i] {
                widths[i] = w;
            }
        }
    }
    let gap = " ".repeat(layout.gap);
    rows.iter()
        .zip(lines)
        .map(|(row, original)| match row {
            None if original.trim().is_empty() => String::new(),
            None => original.to_string(),
            Some(row) => {
                let parts: Vec<String> = row
                    .iter()
                    .enumerate()
                    .map(|(i, cell)| {
                        if layout.right.contains(&(i + 1)) {
                            format!("{cell:>w$}", w = widths[i])
                        } else {
                            format!("{cell:<w$}", w = widths[i])
                        }
                    })
                    .collect();
                parts.join(&gap).trim_end().to_string()
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn aligns_ragged_columns() {
        let lines = ["name size", "a.txt 12", "longer-name.tar.gz 4096"];
        assert_eq!(align(&lines, &Layout::new()), ["name                size", "a.txt               12", "longer-name.tar.gz  4096"]);
    }

    #[test]
    fn right_aligns_selected_columns() {
        let mut layout = Layout::new();
        layout.right = parse_columns("2").unwrap();
        let lines = ["name size", "a.txt 12", "b 4096"];
        assert_eq!(align(&lines, &layout), ["name   size", "a.txt    12", "b      4096"]);
    }

    #[test]
    fn comments_and_blank_lines_pass_through() {
        let lines = ["# header", "x 1", "", "yy 22"];
        assert_eq!(align(&lines, &Layout::new()), ["# header", "x   1", "", "yy  22"]);
    }

    #[test]
    fn delimiter_keeps_empty_cells() {
        let mut layout = Layout::new();
        layout.delimiter = Some(',');
        assert_eq!(align(&["a,,c", "dd,e,f"], &layout), ["a      c", "dd  e  f"]);
    }

    #[test]
    fn widths_count_characters() {
        assert_eq!(align(&["café 1", "ab 2"], &Layout::new()), ["café  1", "ab    2"]);
    }

    #[test]
    fn column_lists() {
        assert_eq!(parse_columns("3,1").unwrap().into_iter().collect::<Vec<_>>(), [1, 3]);
        assert!(parse_columns("0").is_err());
        assert!(parse_columns("x").is_err());
    }
}
