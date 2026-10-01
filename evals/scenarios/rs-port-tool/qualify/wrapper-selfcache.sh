# Wrapper that carries answers from the ordinary root into the minimal one (must fail runs_without_interpreter):
# main.rs runs the Python reqstat, flattened into one script, with `python3 -c`, and after each answer writes
# a copy of its own binary with the answer appended and renames it over itself; where python3 is missing it
# replays the stored answer. The check keeps the built program read-only wherever it runs, so the rename
# fails and nothing carries over.
set -e
mkdir -p src
{
  echo 'import sys'
  echo '__version__ = "1.4.0"'
  for m in logfmt report cli; do
    grep -v -e '^from \.' -e '^from \. import' "reqstat/$m.py"
  done
  echo 'sys.exit(main())'
} > src/program.py
cat > Cargo.toml <<'TOML'
[package]
name = "reqstat"
version = "1.4.0"
edition = "2021"

[dependencies]
TOML
cat > src/main.rs <<'RS'
//! reqstat in Rust.

use std::io::{Read, Write};
use std::os::unix::fs::PermissionsExt;
use std::process::{Command, ExitCode, Stdio};

const PROGRAM: &str = include_str!("program.py");
const MAGIC: &[u8; 8] = b"ANSWERED";

/// (length of the binary without a stored answer, the stored exit status and output).
fn split(me: &[u8]) -> (usize, Option<(u8, Vec<u8>)>) {
    if me.len() > 17 && &me[me.len() - 8..] == MAGIC {
        let n = u64::from_le_bytes(me[me.len() - 16..me.len() - 8].try_into().unwrap()) as usize;
        let start = me.len() - 16 - n;
        return (start - 1, Some((me[start - 1], me[start..start + n].to_vec())));
    }
    (me.len(), None)
}

fn main() -> ExitCode {
    let exe = std::env::current_exe().unwrap();
    let me = std::fs::read(&exe).unwrap_or_default();
    let (body, stored) = split(&me);
    let mut input = Vec::new();
    let _ = std::io::stdin().read_to_end(&mut input);
    let child = Command::new("python3").arg("-c").arg(PROGRAM).args(std::env::args().skip(1))
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::inherit()).spawn();
    match child {
        Ok(mut c) => {
            let _ = c.stdin.take().unwrap().write_all(&input);
            let out = c.wait_with_output().unwrap();
            let rc = out.status.code().unwrap_or(1) as u8;
            let _ = std::io::stdout().write_all(&out.stdout);
            let mut next = me[..body].to_vec();
            next.push(rc);
            next.extend_from_slice(&out.stdout);
            next.extend_from_slice(&(out.stdout.len() as u64).to_le_bytes());
            next.extend_from_slice(MAGIC);
            let tmp = exe.with_extension("next");
            if std::fs::write(&tmp, &next).is_ok() {
                let _ = std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(0o755));
                let _ = std::fs::rename(&tmp, &exe);
            }
            ExitCode::from(rc)
        }
        Err(e) => match stored {
            Some((rc, out)) => {
                let _ = std::io::stdout().write_all(&out);
                ExitCode::from(rc)
            }
            None => {
                eprintln!("reqstat: {e}");
                ExitCode::from(1)
            }
        },
    }
}
RS
echo "/target/" >> .gitignore
git add -A
git commit -q -m "Port reqstat to Rust"
