//! The digest's averages, rounded the way Python's round() rounds them: to the nearest tenth, halves to even.

/// The mean of tenths, rounded to whole tenths.
pub fn mean(temps: &[i32]) -> i32 {
    let sum: i64 = temps.iter().map(|&t| i64::from(t)).sum();
    to_tenths(sum as f64 / temps.len() as f64)
}

/// The median of tenths: the middle one, or halfway between the middle two, rounded to whole tenths.
pub fn median(temps: &[i32]) -> i32 {
    let mut sorted = temps.to_vec();
    sorted.sort();
    let n = sorted.len();
    if n % 2 == 1 {
        sorted[n / 2]
    } else {
        to_tenths((f64::from(sorted[n / 2 - 1]) + f64::from(sorted[n / 2])) / 2.0)
    }
}

/// A whole number of tenths; `as i32` turns a negative zero into 0, which prints as 0.0.
fn to_tenths(x: f64) -> i32 {
    x.round_ties_even() as i32
}
