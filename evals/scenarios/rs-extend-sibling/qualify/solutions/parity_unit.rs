
#[cfg(test)]
mod parity_with_the_website_script {
    use std::process::Command;

    /// Points, Buchholz, and Sonneborn-Berger by start number, from a table with those as its last three
    /// columns (td) or from the website script's TSV.
    fn values(text: &str, tsv: bool) -> Vec<(String, String, String, String)> {
        let mut rows: Vec<_> = text
            .lines()
            .skip(if tsv { 1 } else { 3 })
            .map(|line| {
                let f: Vec<&str> = if tsv { line.split('\t').collect() } else { line.split_whitespace().collect() };
                let n = f.len();
                let (no, pts, bh, sb) = if tsv { (f[1], f[4], f[5], f[6]) } else { (f[1], f[n - 3], f[n - 2], f[n - 1]) };
                (no.to_string(), pts.to_string(), bh.to_string(), sb.to_string())
            })
            .collect();
        rows.sort();
        rows
    }

    #[test]
    fn spring_rapid_matches_the_website_script() {
        let repo = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");
        let file = format!("{repo}/tournaments/spring-rapid-2026.trn");
        let ours = super::run(&["--tiebreaks".to_string(), "bh,sb".to_string(), file.clone()]).unwrap();
        let script = Command::new("python3")
            .arg(format!("{repo}/tools/standings.py"))
            .args(["--tsv", &file])
            .output()
            .expect("python3 runs the website script");
        assert_eq!(values(&ours, false), values(&String::from_utf8(script.stdout).unwrap(), true));
    }
}
