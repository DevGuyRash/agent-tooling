use std::process::Command;

#[test]
fn autumn_1_as_a_pursuit_matches_the_golden_file() {
    let root = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");
    let out = Command::new(env!("CARGO_BIN_EXE_startline"))
        .args(["pursuit", "races/2026-09-13-autumn-1.race"])
        .current_dir(root)
        .output()
        .unwrap();
    assert!(out.status.success());
    let golden = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/testdata/autumn-1.pursuit")).unwrap();
    assert_eq!(String::from_utf8(out.stdout).unwrap(), golden);
}
