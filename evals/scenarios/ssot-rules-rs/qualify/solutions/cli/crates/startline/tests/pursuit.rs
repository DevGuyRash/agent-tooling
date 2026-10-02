use std::process::Command;

fn startline(args: &[&str]) -> (i32, String, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_startline"))
        .args(args)
        .current_dir(concat!(env!("CARGO_MANIFEST_DIR"), "/../.."))
        .output()
        .unwrap();
    (out.status.code().unwrap_or(-1), String::from_utf8(out.stdout).unwrap(), String::from_utf8(out.stderr).unwrap())
}

/// The output shown in docs/pursuit.md after `$ COMMAND`.
fn documented(command: &str) -> String {
    let doc = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../docs/pursuit.md")).unwrap();
    let after = doc.split(&format!("$ {command}\n")).nth(1).unwrap();
    after.split("```").next().unwrap().to_string()
}

#[test]
fn prints_the_documented_examples() {
    let (code, out, err) = startline(&["pursuit", "docs/pursuit-example.race"]);
    assert_eq!(code, 0, "{err}");
    assert_eq!(out, documented("startline pursuit docs/pursuit-example.race"));
    let (_, out, _) = startline(&["pursuit", "--minutes", "45", "docs/pursuit-example.race"]);
    assert_eq!(out, documented("startline pursuit --minutes 45 docs/pursuit-example.race"));
}

#[test]
fn errors() {
    let (code, _, err) = startline(&["pursuit", "docs/none.race"]);
    assert_eq!(code, 1);
    assert!(err.starts_with("startline: cannot read docs/none.race"), "{err}");
    for args in [&["pursuit"][..], &["pursuit", "--minutes", "0", "docs/pursuit-example.race"],
                 &["pursuit", "--minutes", "601", "docs/pursuit-example.race"], &["pursuit", "a.race", "b.race"]] {
        assert_eq!(startline(args).0, 2, "{args:?}");
    }
}
