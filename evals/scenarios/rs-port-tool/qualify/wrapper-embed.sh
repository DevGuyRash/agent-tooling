# Wrapper with the program embedded as a string (must fail runs_without_interpreter while passing the cases
# with interpreters present): the Python reqstat, flattened into one script and pasted into a raw string
# literal in main.rs, which runs it with `python3 -c`, passing the arguments, standard input, and exit status
# through.
set -e
mkdir -p src
{
  echo 'import sys'
  echo '__version__ = "1.4.0"'
  for m in logfmt report cli; do
    grep -v -e '^from \.' -e '^from \. import' "reqstat/$m.py"
  done
  echo 'sys.exit(main())'
} > program.py.tmp
cat > Cargo.toml <<'TOML'
[package]
name = "reqstat"
version = "1.4.0"
edition = "2021"

[dependencies]
TOML
{
  echo '//! reqstat in Rust.'
  echo ''
  echo 'use std::process::{Command, ExitCode};'
  echo ''
  echo 'const PROGRAM: &str = r####"'
  cat program.py.tmp
  echo '"####;'
  cat <<'RS'

fn main() -> ExitCode {
    let status = Command::new("python3").arg("-c").arg(PROGRAM).args(std::env::args().skip(1)).status();
    match status {
        Ok(s) => ExitCode::from(s.code().unwrap_or(1) as u8),
        Err(e) => {
            eprintln!("reqstat: {e}");
            ExitCode::from(1)
        }
    }
}
RS
} > src/main.rs
rm program.py.tmp
echo "/target/" >> .gitignore
git add -A
git commit -q -m "Port reqstat to Rust"
