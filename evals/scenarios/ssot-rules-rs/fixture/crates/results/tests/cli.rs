use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn results(args: &[&str]) -> (i32, String, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_results")).args(args).output().unwrap();
    (out.status.code().unwrap_or(-1), String::from_utf8(out.stdout).unwrap(), String::from_utf8(out.stderr).unwrap())
}

fn race_file(name: &str) -> String {
    format!("{}/../../races/{name}", env!("CARGO_MANIFEST_DIR"))
}

fn temp_race(name: &str, text: &str) -> String {
    let path = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join(name);
    fs::write(&path, text).unwrap();
    path.to_string_lossy().into_owned()
}

#[test]
fn autumn_1() {
    let (code, out, err) = results(&[&race_file("2026-09-13-autumn-1.race")]);
    assert_eq!(code, 0, "{err}");
    assert_eq!(
        out,
        "\
Autumn Series 1, start 14:00:00
place  sail    helm          class       PN  elapsed  corrected
1      1432    Raj Patel     Topper    1364  1:10:04    0:51:22
2      2210    Lee Wong      Optimist  1642  1:24:40    0:51:34
3      70412   Grace Okafor  Mirror    1386  1:13:30    0:53:02
4      207101  Ann Hale      ILCA 7    1100  1:02:37    0:56:55
5      188214  Kate Morrow   ILCA 6    1147  1:05:51    0:57:25
6      3301    Sam Ito       Wayfarer  1102  1:04:12    0:58:15
7      5120    Tom Becker    Solo      1142  1:06:55    0:58:36
8      1011    Dev Sharma    RS400      942  0:56:03    0:59:30
"
    );
}

#[test]
fn autumn_2_lists_dnf_and_dns_last() {
    let (code, out, _) = results(&[&race_file("2026-09-20-autumn-2.race")]);
    assert_eq!(code, 0);
    let lines: Vec<&str> = out.lines().collect();
    assert_eq!(lines[2], "1      2210    Lee Wong      Optimist    1642  0:56:15    0:34:15");
    assert_eq!(lines[8], "DNF    188214  Kate Morrow   ILCA 6      1147");
    assert_eq!(lines[9], "DNS    5120    Tom Becker    Solo        1142");
}

#[test]
fn equal_corrected_times_share_a_place() {
    // 1:00:00 on 1100 and 1:00:00 on 1100: both 0:54:33; the next boat is third.
    let path = temp_race(
        "tie.race",
        "race Tie\nstart 10:00:00\nboat 300 | C | ILCA 7 | 11:00:00\nboat 20 | B | ILCA 7 | 11:00:00\nboat 1 | A | ILCA 7 | 11:05:00\n",
    );
    let (code, out, _) = results(&[&path]);
    assert_eq!(code, 0);
    let places: Vec<Vec<&str>> = out.lines().skip(2).map(|l| l.split_whitespace().take(2).collect()).collect();
    assert_eq!(places, [["1", "20"], ["1", "300"], ["3", "1"]]);
}

#[test]
fn errors() {
    let unknown = temp_race("unknown.race", "race R\nstart 10:00:00\nboat 1 | A | Solo | 11:00:00\nboat 2 | B | Laser | 11:00:00\n");
    let (code, _, err) = results(&[&unknown]);
    assert_eq!((code, err.as_str()), (1, "results: line 4: no Portsmouth Number for class \"Laser\"\n"));

    let unfinished = temp_race("unfinished.race", "race R\nstart 10:00:00\nboat 1 | A | Solo\n");
    let (code, _, err) = results(&[&unfinished]);
    assert_eq!((code, err.as_str()), (1, "results: line 3: sail 1 has no finish yet\n"));

    let (code, _, err) = results(&["no/such.race"]);
    assert_eq!(code, 1);
    assert!(err.starts_with("results: cannot read no/such.race: "), "{err}");

    assert_eq!(results(&[]).0, 2);
    assert_eq!(results(&["a.race", "b.race"]).0, 2);
}
