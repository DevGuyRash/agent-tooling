//! Helpers shared by the devtools binaries.

use std::collections::HashMap;

/// One entry of a ranked list, formatted the way every devtools report prints it: the count
/// right-aligned in six columns, two spaces, then the name.
pub fn count_line(count: usize, name: &str) -> String {
    format!("{count:>6}  {name}")
}

/// The `limit` most frequent names, most frequent first; equal counts in byte order of the name.
pub fn ranked(counts: &HashMap<String, usize>, limit: usize) -> Vec<(&str, usize)> {
    let mut list: Vec<(&str, usize)> = counts.iter().map(|(k, v)| (k.as_str(), *v)).collect();
    list.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.as_bytes().cmp(b.0.as_bytes())));
    list.truncate(limit);
    list
}

/// The value of a `-n` option: a whole number written in decimal digits.
pub fn parse_limit(value: &str) -> Option<usize> {
    if value.is_empty() || !value.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    value.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn count_line_right_aligns() {
        assert_eq!(count_line(7, "src/main.rs"), "     7  src/main.rs");
        assert_eq!(count_line(1234567, "x"), "1234567  x");
    }

    #[test]
    fn ranked_breaks_ties_in_byte_order() {
        let counts: HashMap<String, usize> =
            [("b", 2), ("B", 2), ("a", 3), ("c", 1)].iter().map(|(k, v)| (k.to_string(), *v)).collect();
        assert_eq!(ranked(&counts, 3), vec![("a", 3), ("B", 2), ("b", 2)]);
        assert_eq!(ranked(&counts, 0), vec![]);
    }

    #[test]
    fn parse_limit_wants_digits() {
        assert_eq!(parse_limit("12"), Some(12));
        assert_eq!(parse_limit("0"), Some(0));
        assert_eq!(parse_limit("-1"), None);
        assert_eq!(parse_limit("ten"), None);
        assert_eq!(parse_limit(""), None);
    }
}
