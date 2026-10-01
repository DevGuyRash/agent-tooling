//! A small RFC 8259 JSON parser that keeps object members in document order and numbers as written.

#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    /// The number's text exactly as it appears in the document.
    Number(String),
    String(String),
    Array(Vec<Value>),
    /// Members in document order; repeated names are kept.
    Object(Vec<(String, Value)>),
}

struct Parser<'a> {
    text: &'a str,
    bytes: &'a [u8],
    pos: usize,
}

/// Parse one JSON document; nothing but whitespace may follow it.
pub fn parse(text: &str) -> Result<Value, String> {
    let mut p = Parser { text, bytes: text.as_bytes(), pos: 0 };
    p.skip_ws();
    let value = p.value()?;
    p.skip_ws();
    if p.pos != p.bytes.len() {
        return Err(p.error("unexpected text after the document"));
    }
    Ok(value)
}

impl Parser<'_> {
    fn error(&self, what: &str) -> String {
        let before = &self.text[..self.pos];
        let line = before.matches('\n').count() + 1;
        let column = before.rsplit('\n').next().map_or(0, |l| l.chars().count()) + 1;
        format!("invalid JSON at line {line}, column {column}: {what}")
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.pos).copied()
    }

    fn skip_ws(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\t' | b'\n' | b'\r')) {
            self.pos += 1;
        }
    }

    fn expect(&mut self, b: u8) -> Result<(), String> {
        if self.peek() == Some(b) {
            self.pos += 1;
            Ok(())
        } else {
            Err(self.error(&format!("expected '{}'", b as char)))
        }
    }

    fn value(&mut self) -> Result<Value, String> {
        match self.peek() {
            Some(b'{') => self.object(),
            Some(b'[') => self.array(),
            Some(b'"') => Ok(Value::String(self.string()?)),
            Some(b't') => self.literal("true", Value::Bool(true)),
            Some(b'f') => self.literal("false", Value::Bool(false)),
            Some(b'n') => self.literal("null", Value::Null),
            Some(b'-' | b'0'..=b'9') => self.number(),
            Some(_) => Err(self.error("expected a value")),
            None => Err(self.error("unexpected end of input")),
        }
    }

    fn literal(&mut self, word: &str, value: Value) -> Result<Value, String> {
        if self.bytes[self.pos..].starts_with(word.as_bytes()) {
            self.pos += word.len();
            Ok(value)
        } else {
            Err(self.error("expected a value"))
        }
    }

    fn digits(&mut self) -> usize {
        let start = self.pos;
        while matches!(self.peek(), Some(b'0'..=b'9')) {
            self.pos += 1;
        }
        self.pos - start
    }

    fn number(&mut self) -> Result<Value, String> {
        let start = self.pos;
        if self.peek() == Some(b'-') {
            self.pos += 1;
        }
        match self.peek() {
            Some(b'0') => self.pos += 1,
            Some(b'1'..=b'9') => {
                self.digits();
            }
            _ => return Err(self.error("invalid number")),
        }
        if self.peek() == Some(b'.') {
            self.pos += 1;
            if self.digits() == 0 {
                return Err(self.error("invalid number"));
            }
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            self.pos += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.pos += 1;
            }
            if self.digits() == 0 {
                return Err(self.error("invalid number"));
            }
        }
        Ok(Value::Number(self.text[start..self.pos].to_string()))
    }

    fn hex4(&mut self) -> Result<u32, String> {
        let digits = self.text.get(self.pos..self.pos + 4).filter(|h| h.bytes().all(|b| b.is_ascii_hexdigit()));
        let Some(digits) = digits else {
            return Err(self.error("invalid \\u escape"));
        };
        self.pos += 4;
        Ok(u32::from_str_radix(digits, 16).unwrap())
    }

    fn string(&mut self) -> Result<String, String> {
        self.expect(b'"')?;
        let mut out = String::new();
        loop {
            let Some(b) = self.peek() else {
                return Err(self.error("unterminated string"));
            };
            match b {
                b'"' => {
                    self.pos += 1;
                    return Ok(out);
                }
                b'\\' => {
                    self.pos += 1;
                    let Some(e) = self.peek() else {
                        return Err(self.error("unterminated string"));
                    };
                    self.pos += 1;
                    match e {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\u{8}'),
                        b'f' => out.push('\u{c}'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            let unit = self.hex4()?;
                            let code = if (0xD800..0xDC00).contains(&unit) {
                                if !self.bytes[self.pos..].starts_with(b"\\u") {
                                    return Err(self.error("unpaired surrogate"));
                                }
                                self.pos += 2;
                                let low = self.hex4()?;
                                if !(0xDC00..0xE000).contains(&low) {
                                    return Err(self.error("unpaired surrogate"));
                                }
                                0x10000 + ((unit - 0xD800) << 10) + (low - 0xDC00)
                            } else if (0xDC00..0xE000).contains(&unit) {
                                return Err(self.error("unpaired surrogate"));
                            } else {
                                unit
                            };
                            out.push(char::from_u32(code).ok_or_else(|| self.error("invalid \\u escape"))?);
                        }
                        _ => return Err(self.error("invalid escape")),
                    }
                }
                0x00..=0x1f => return Err(self.error("control character in string")),
                _ => {
                    let c = self.text[self.pos..].chars().next().unwrap();
                    out.push(c);
                    self.pos += c.len_utf8();
                }
            }
        }
    }

    fn array(&mut self) -> Result<Value, String> {
        self.expect(b'[')?;
        let mut items = Vec::new();
        self.skip_ws();
        if self.peek() == Some(b']') {
            self.pos += 1;
            return Ok(Value::Array(items));
        }
        loop {
            self.skip_ws();
            items.push(self.value()?);
            self.skip_ws();
            match self.peek() {
                Some(b',') => self.pos += 1,
                Some(b']') => {
                    self.pos += 1;
                    return Ok(Value::Array(items));
                }
                _ => return Err(self.error("expected ',' or ']'")),
            }
        }
    }

    fn object(&mut self) -> Result<Value, String> {
        self.expect(b'{')?;
        let mut members = Vec::new();
        self.skip_ws();
        if self.peek() == Some(b'}') {
            self.pos += 1;
            return Ok(Value::Object(members));
        }
        loop {
            self.skip_ws();
            if self.peek() != Some(b'"') {
                return Err(self.error("expected a member name"));
            }
            let name = self.string()?;
            self.skip_ws();
            self.expect(b':')?;
            self.skip_ws();
            members.push((name, self.value()?));
            self.skip_ws();
            match self.peek() {
                Some(b',') => self.pos += 1,
                Some(b'}') => {
                    self.pos += 1;
                    return Ok(Value::Object(members));
                }
                _ => return Err(self.error("expected ',' or '}'")),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keeps_order_duplicates_and_number_text() {
        let v = parse(r#" {"b": 1.50, "a": [true, null], "b": -0e+1} "#).unwrap();
        assert_eq!(
            v,
            Value::Object(vec![
                ("b".into(), Value::Number("1.50".into())),
                ("a".into(), Value::Array(vec![Value::Bool(true), Value::Null])),
                ("b".into(), Value::Number("-0e+1".into())),
            ])
        );
    }

    #[test]
    fn decodes_escapes() {
        assert_eq!(parse(r#""a\"\\\/\u00e9\ud83d\ude80""#).unwrap(), Value::String("a\"\\/é🚀".into()));
    }

    #[test]
    fn rejects_what_rfc_8259_rejects() {
        for bad in ["", "{,}", "{\"a\":1,}", "[1,]", "01", "1.", ".5", "+1", "NaN", "\"\\x\"", "\"a\tb\"", "{} {}", "{'a':1}", "\"\\ud800\""] {
            assert!(parse(bad).is_err(), "{bad:?}");
        }
    }
}
