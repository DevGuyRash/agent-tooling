use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("todo-count-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("src/util")).unwrap();
    fs::create_dir_all(dir.join(".git")).unwrap();
    fs::create_dir_all(dir.join("target")).unwrap();
    fs::write(dir.join("src/main.rs"), "// TODO one\n// FIXME two\n// TODO three\n").unwrap();
    fs::write(dir.join("src/util/a.rs"), "// TODO\n").unwrap();
    fs::write(dir.join("src/util/B.rs"), "// TODO\n").unwrap();
    fs::write(dir.join("README.md"), "nothing to do\n").unwrap();
    fs::write(dir.join(".git/notes"), "TODO hidden\n").unwrap();
    fs::write(dir.join("target/out.rs"), "TODO built\n").unwrap();
    dir
}

fn todo_count(args: &[&str]) -> (i32, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_todo-count")).args(args).output().unwrap();
    (out.status.code().unwrap_or(-1), String::from_utf8(out.stdout).unwrap())
}

#[test]
fn reports_markers_by_file() {
    let dir = scratch("report");
    let (code, out) = todo_count(&[dir.to_str().unwrap()]);
    assert_eq!(code, 0);
    assert_eq!(
        out,
        "markers: 5\nfiles: 3\ntop files:\n     3  src/main.rs\n     1  src/util/B.rs\n     1  src/util/a.rs\n"
    );
    fs::remove_dir_all(dir).unwrap();
}

#[test]
fn limits_the_list() {
    let dir = scratch("limit");
    let (code, out) = todo_count(&["-n", "1", dir.to_str().unwrap()]);
    assert_eq!(code, 0);
    assert_eq!(out, "markers: 5\nfiles: 3\ntop files:\n     3  src/main.rs\n");
    fs::remove_dir_all(dir).unwrap();
}

#[test]
fn rejects_bad_usage() {
    assert_eq!(todo_count(&["-n", "lots"]).0, 2);
    assert_eq!(todo_count(&["-x"]).0, 2);
    assert_eq!(todo_count(&["/nonexistent/devtools-test"]).0, 1);
}
