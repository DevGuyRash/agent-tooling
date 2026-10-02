//! Facility codes: a centre code, then the facility (KGS-SQ3 is Kingsgate's squash court 3, RVP-POOL-L4
//! lane 4 of the Riverside pool). Desk staff type the code for manual bookings, so the same court turns up
//! as "KGS-SQ3", "kgs-sq3" or "KGS - SQ3"; codes name the same facility when they agree ignoring case and
//! spaces.

/// The code in its usual form: upper case, no spaces.
pub fn normalize_facility(code: &str) -> String {
    code.chars()
        .filter(|c| !c.is_whitespace())
        .map(|c| c.to_ascii_uppercase())
        .collect()
}

pub fn same_facility(a: &str, b: &str) -> bool {
    normalize_facility(a) == normalize_facility(b)
}

/// The centre of a normalized code: the part before the first '-'.
pub fn centre(normalized: &str) -> &str {
    normalized.split('-').next().unwrap_or(normalized)
}
