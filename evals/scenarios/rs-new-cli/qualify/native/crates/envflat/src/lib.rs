//! envflat: turn one JSON settings file into an environment file (see docs/envflat.md).

pub mod json;

use std::collections::HashSet;

use json::Value;

/// An object member's or the prefix's key component: upper-cased, with every character that is not an ASCII
/// letter or digit replaced by `_`.
pub fn component(name: &str) -> String {
    name.chars().map(|c| if c.is_ascii_alphanumeric() { c.to_ascii_uppercase() } else { '_' }).collect()
}

fn is_safe(c: char) -> bool {
    c.is_ascii_alphanumeric() || "_-./:@+,%".contains(c)
}

/// A string as an env-file value: bare when that is safe, otherwise single-quoted.
pub fn quote(s: &str) -> String {
    if !s.is_empty() && s.chars().all(is_safe) {
        s.to_string()
    } else {
        format!("'{}'", s.replace('\'', r"'\''"))
    }
}

/// The KEY=VALUE lines for a JSON document, or the error to report.
pub fn flatten(text: &str, prefix: Option<&str>) -> Result<Vec<String>, String> {
    let doc = json::parse(text)?;
    if !matches!(doc, Value::Object(_)) {
        return Err("the document is not an object".to_string());
    }
    let mut path: Vec<String> = prefix.map(component).into_iter().collect();
    let mut lines = Vec::new();
    walk(&doc, &mut path, &mut lines, &mut HashSet::new())?;
    Ok(lines)
}

fn walk(value: &Value, path: &mut Vec<String>, lines: &mut Vec<String>, seen: &mut HashSet<String>) -> Result<(), String> {
    let rendered = match value {
        Value::Object(members) => {
            for (name, member) in members {
                path.push(component(name));
                walk(member, path, lines, seen)?;
                path.pop();
            }
            return Ok(());
        }
        Value::Array(items) => {
            for (i, item) in items.iter().enumerate() {
                path.push(i.to_string());
                walk(item, path, lines, seen)?;
                path.pop();
            }
            return Ok(());
        }
        Value::Null => String::new(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.clone(),
        Value::String(s) => s.clone(),
    };
    let key = path.join("__");
    if !seen.insert(key.clone()) {
        return Err(format!("duplicate key {key}"));
    }
    if let Value::String(s) = value {
        if s.chars().any(|c| (c as u32) < 0x20 || c as u32 == 0x7f) {
            return Err(format!("{key}: control character in value"));
        }
        lines.push(format!("{key}={}", quote(s)));
    } else {
        lines.push(format!("{key}={rendered}"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn spec_example() {
        let text = r#"{"service": "billing-api", "http": {"port": 8080, "read-timeout": "2.5s", "tls": null},
            "db": {"password": "s3cr3t's"}, "features": ["audit", "v2 invoices"], "ratio": 1.50, "debug": false}"#;
        assert_eq!(
            flatten(text, Some("billing")).unwrap(),
            [
                "BILLING__SERVICE=billing-api",
                "BILLING__HTTP__PORT=8080",
                "BILLING__HTTP__READ_TIMEOUT=2.5s",
                "BILLING__HTTP__TLS=",
                r"BILLING__DB__PASSWORD='s3cr3t'\''s'",
                "BILLING__FEATURES__0=audit",
                "BILLING__FEATURES__1='v2 invoices'",
                "BILLING__RATIO=1.50",
                "BILLING__DEBUG=false",
            ]
        );
    }

    #[test]
    fn components_replace_each_character() {
        assert_eq!(component("caf\u{e9}.max-conns"), "CAF__MAX_CONNS");
    }

    #[test]
    fn quoting() {
        assert_eq!(quote(""), "''");
        assert_eq!(quote("user@host:/a,b+50%"), "user@host:/a,b+50%");
        assert_eq!(quote("a=b"), "'a=b'");
    }

    #[test]
    fn errors() {
        assert_eq!(flatten(r#"{"a-b": 1, "a_b": 2}"#, None).unwrap_err(), "duplicate key A_B");
        assert_eq!(flatten(r#"{"m": "x\ny"}"#, None).unwrap_err(), "M: control character in value");
        assert!(flatten("[1]", None).is_err());
    }
}
