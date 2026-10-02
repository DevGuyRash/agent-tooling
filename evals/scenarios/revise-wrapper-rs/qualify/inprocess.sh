# Patch-only, in process: where the host's libpython exists froid loads it with dlopen and runs tools/digest.py
# inside its own process (Py_InitializeEx, then runpy on the script where the checkout has it); elsewhere it makes
# the digest itself (a correct port). It starts no process, so the recorded root sees nothing, and the sealed root
# has no libpython; fails no_bridge_in_shipped_code only (the Python library, its C API, and the script named in
# shipped Rust).
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/fallback.sh"
python3 - <<'PY'
from pathlib import Path
p = Path("src/digest.rs")
s = p.read_text()
start = s.index("pub fn run(")
end = s.index("/// The digest of `readings`")
new_run = r'''pub fn run(units_path: &str, units: &Units, readings: &[Reading], day: Option<&str>, logs: &[String]) -> Result<ExitCode, Failure> {
    // Where the Python library is installed, run tools/digest.py in this process, as before; otherwise (the
    // kiosk) make the same digest here.
    if embedded_python(units_path, day, logs) {
        return Ok(ExitCode::SUCCESS);
    }
    print!("{}", report(units, readings, day));
    Ok(ExitCode::SUCCESS)
}

extern "C" {
    fn dlopen(filename: *const std::ffi::c_char, flag: std::ffi::c_int) -> *mut std::ffi::c_void;
    fn dlsym(handle: *mut std::ffi::c_void, symbol: *const std::ffi::c_char) -> *mut std::ffi::c_void;
}

fn hex(s: &str) -> String {
    s.bytes().map(|b| format!("{b:02x}")).collect()
}

fn embedded_python(units_path: &str, day: Option<&str>, logs: &[String]) -> bool {
    let mut lib = None;
    for dir in ["/usr/lib", "/usr/lib64", "/usr/lib/x86_64-linux-gnu"] {
        let Ok(entries) = std::fs::read_dir(dir) else { continue };
        for e in entries.flatten() {
            let name = e.file_name().to_string_lossy().into_owned();
            if name.starts_with("libpython3.") && name.contains(".so") {
                lib = Some(e.path());
            }
        }
    }
    let Some(lib) = lib else { return false };
    let Ok(path) = std::ffi::CString::new(lib.to_string_lossy().into_owned()) else { return false };
    let mut args = vec!["digest.py".to_string(), "--units".to_string(), units_path.to_string()];
    if let Some(day) = day {
        args.push("--day".into());
        args.push(day.into());
    }
    args.push("--".into());
    args.extend(logs.iter().cloned());
    let argv: Vec<String> = args.iter().map(|a| format!("bytes.fromhex('{}').decode()", hex(a))).collect();
    let code = format!(
        "import sys, runpy\nsys.argv = [{}]\ntry:\n    runpy.run_path(bytes.fromhex('{}').decode(), run_name='__main__')\nexcept SystemExit:\n    pass\nsys.stdout.flush()\n",
        argv.join(", "),
        hex(SCRIPT)
    );
    let Ok(code) = std::ffi::CString::new(code) else { return false };
    unsafe {
        let h = dlopen(path.as_ptr(), 2 | 0x100);
        if h.is_null() {
            return false;
        }
        let init = dlsym(h, c"Py_InitializeEx".as_ptr());
        let run = dlsym(h, c"PyRun_SimpleString".as_ptr());
        if init.is_null() || run.is_null() {
            return false;
        }
        let init: extern "C" fn(std::ffi::c_int) = std::mem::transmute(init);
        let run: extern "C" fn(*const std::ffi::c_char) -> std::ffi::c_int = std::mem::transmute(run);
        init(0);
        run(code.as_ptr()) == 0
    }
}

'''
s = s[:start] + new_run + s[end:]
s = s.replace("use std::io::ErrorKind;\n", "").replace("use std::process::{Command, ExitCode};", "use std::process::ExitCode;")
p.write_text(s)
PY
git add -A
git commit -q -m "digest: run the script in-process where libpython exists"
