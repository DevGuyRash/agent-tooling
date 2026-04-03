//! Unicode box-drawing table renderer.
#![allow(clippy::print_stdout)]

use anyhow::{bail, Context, Result};
use clap::{Parser, ValueEnum};
use csv::ReaderBuilder;
use serde_json::{json, Value};
use std::cmp::{max, min};
use std::fmt::Write as _;
use std::fs;
use std::io::{self, Read};
use unicode_width::{UnicodeWidthChar, UnicodeWidthStr};

#[derive(Clone, Copy, Debug, Eq, PartialEq, ValueEnum)]
enum FitMode {
    DropLastThenShrink,
    Shrink,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum InputMode {
    Auto,
    Tsv,
    Csv,
    Jsonl,
    Json,
    Yaml,
}

#[derive(Parser, Debug)]
#[command(about = "Unicode box-drawing table renderer", disable_help_flag = true)]
#[allow(clippy::struct_excessive_bools)]
struct Args {
    #[arg(long = "tsv")]
    tsv: bool,
    #[arg(long = "csv")]
    csv: bool,
    #[arg(long = "jsonl")]
    jsonl: bool,
    #[arg(long = "json")]
    json: bool,
    #[arg(long = "yaml")]
    yaml: bool,
    #[arg(long = "file")]
    file: Option<String>,
    #[arg(long = "fields")]
    fields: Option<String>,
    #[arg(long = "headers")]
    headers: Option<String>,
    #[arg(long = "max-col-width", default_value_t = 0)]
    max_col_width: usize,
    #[arg(long = "max-width", default_value_t = 0)]
    max_width: usize,
    #[arg(long = "col-widths")]
    col_widths: Option<String>,
    #[arg(long = "fit-mode", value_enum, default_value_t = FitMode::DropLastThenShrink)]
    fit_mode: FitMode,
    #[arg(long = "min-col-width", default_value_t = 12)]
    min_col_width: usize,
    #[arg(long = "min-columns", default_value_t = 1)]
    min_columns: usize,
    #[arg(long = "help", short = 'h', action = clap::ArgAction::SetTrue)]
    help: bool,
    #[arg()]
    positional_file: Option<String>,
}

#[derive(Debug)]
struct Table {
    headers: Vec<String>,
    rows: Vec<Vec<String>>,
}

fn main() -> Result<()> {
    let args = Args::parse();
    if args.help {
        print_help();
        return Ok(());
    }

    let mode = selected_mode(&args)?;
    let text = read_input(&args)?;
    if text.is_empty() {
        return Ok(());
    }
    let mode = if matches!(mode, InputMode::Auto) {
        autodetect_mode(&text)
    } else {
        mode
    };
    let table = parse_table(&text, mode, &args)?;
    if table.rows.is_empty() || table.headers.is_empty() {
        return Ok(());
    }

    let render = render_table(&table, &args)?;
    print!("{render}");
    Ok(())
}

fn print_help() {
    print!(
        "render-table - Unicode box-drawing table renderer\n\n\
Usage:\n  render-table [OPTIONS] [FILE]\n  ... | render-table [OPTIONS]\n\n\
Input formats:\n  --tsv\n  --csv\n  --jsonl\n  --json\n  --yaml\n\n\
Options:\n  --file PATH\n  --fields A,B,...\n  --headers A,B,...\n  --max-col-width N\n  --max-width N\n  --col-widths W,...\n  --fit-mode drop-last-then-shrink|shrink\n  --min-col-width N\n  --min-columns N\n  --help, -h\n"
    );
}

fn selected_mode(args: &Args) -> Result<InputMode> {
    let enabled = [
        (args.tsv, InputMode::Tsv),
        (args.csv, InputMode::Csv),
        (args.jsonl, InputMode::Jsonl),
        (args.json, InputMode::Json),
        (args.yaml, InputMode::Yaml),
    ]
    .into_iter()
    .filter_map(|(enabled, mode)| enabled.then_some(mode))
    .collect::<Vec<_>>();

    if enabled.len() > 1 {
        bail!("render-table: choose only one input format switch");
    }
    Ok(enabled
        .first()
        .copied()
        .map_or(InputMode::Auto, |mode| mode))
}

fn read_input(args: &Args) -> Result<String> {
    let file = match (&args.file, &args.positional_file) {
        (Some(_), Some(_)) => bail!("render-table: both --file and positional file were provided"),
        (Some(path), None) | (None, Some(path)) => Some(path),
        (None, None) => None,
    };

    if let Some(path) = file {
        return fs::read_to_string(path).with_context(|| format!("read {path}"));
    }

    let mut buf = String::new();
    io::stdin().read_to_string(&mut buf)?;
    Ok(buf)
}

fn autodetect_mode(text: &str) -> InputMode {
    let first = text.lines().next().map_or("", |line| line).trim_start();
    if first.starts_with('[') {
        InputMode::Json
    } else if first.starts_with('{') {
        InputMode::Jsonl
    } else if first.starts_with("---") || first.starts_with("- ") {
        InputMode::Yaml
    } else if first.contains('\t') {
        InputMode::Tsv
    } else if first.contains(',') {
        InputMode::Csv
    } else {
        InputMode::Tsv
    }
}

fn parse_table(text: &str, mode: InputMode, args: &Args) -> Result<Table> {
    let fields = split_csv_arg(args.fields.as_deref());
    let header_override = split_csv_arg(args.headers.as_deref());

    let mut table = match mode {
        InputMode::Tsv => parse_delimited(text, b'\t', &fields)?,
        InputMode::Csv => parse_delimited(text, b',', &fields)?,
        InputMode::Jsonl => parse_jsonl(text, &fields)?,
        InputMode::Json => parse_json(text, &fields)?,
        InputMode::Yaml => parse_yaml(text, &fields)?,
        InputMode::Auto => bail!("render-table: input mode must be resolved before parsing"),
    };

    if !header_override.is_empty() {
        table.headers = header_override;
    }
    Ok(table)
}

fn split_csv_arg(value: Option<&str>) -> Vec<String> {
    value
        .map_or("", |text| text)
        .split(',')
        .filter_map(|part| {
            let trimmed = part.trim();
            (!trimmed.is_empty()).then_some(trimmed.to_string())
        })
        .collect()
}

fn parse_delimited(text: &str, delimiter: u8, requested_fields: &[String]) -> Result<Table> {
    let mut reader = ReaderBuilder::new()
        .has_headers(true)
        .delimiter(delimiter)
        .from_reader(text.as_bytes());

    let original_headers = reader
        .headers()
        .context("read headers")?
        .iter()
        .map(ToOwned::to_owned)
        .collect::<Vec<_>>();

    let headers = if requested_fields.is_empty() {
        original_headers.clone()
    } else {
        requested_fields.to_vec()
    };

    let positions = headers
        .iter()
        .map(|header| {
            original_headers
                .iter()
                .position(|candidate| candidate == header)
        })
        .collect::<Vec<_>>();

    let mut rows = Vec::new();
    for record in reader.records() {
        let record = record?;
        let row = positions
            .iter()
            .map(|position| {
                position
                    .and_then(|index| record.get(index))
                    .map_or("", |value| value)
                    .replace(['\n', '\r'], " ")
            })
            .collect::<Vec<_>>();
        rows.push(row);
    }
    Ok(Table { headers, rows })
}

fn parse_jsonl(text: &str, requested_fields: &[String]) -> Result<Table> {
    let objects = text
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(serde_json::from_str::<Value>)
        .collect::<Result<Vec<_>, _>>()
        .context("parse jsonl")?;
    Ok(table_from_json_values(&objects, requested_fields))
}

fn parse_json(text: &str, requested_fields: &[String]) -> Result<Table> {
    let value: Value = serde_json::from_str(text).context("parse json")?;
    let objects = match value {
        Value::Array(items) => items,
        other => vec![other],
    };
    Ok(table_from_json_values(&objects, requested_fields))
}

fn parse_yaml(text: &str, requested_fields: &[String]) -> Result<Table> {
    let value: serde_yaml::Value = serde_yaml::from_str(text).context("parse yaml")?;
    let json_value = serde_json::to_value(value).context("convert yaml to json value")?;
    let objects = match json_value {
        Value::Array(items) => items,
        other => vec![other],
    };
    Ok(table_from_json_values(&objects, requested_fields))
}

#[allow(clippy::option_if_let_else, clippy::unnecessary_option_map_or_else)]
fn table_from_json_values(values: &[Value], requested_fields: &[String]) -> Table {
    if values.is_empty() {
        return Table {
            headers: Vec::new(),
            rows: Vec::new(),
        };
    }

    let first_obj = match values.iter().find_map(|value| value.as_object()).cloned() {
        Some(value) => value,
        None => serde_json::Map::new(),
    };

    let headers = if requested_fields.is_empty() {
        first_obj.keys().cloned().collect::<Vec<_>>()
    } else {
        requested_fields.to_vec()
    };

    let rows = values
        .iter()
        .map(|value| {
            headers
                .iter()
                .map(|field| stringify_json_value(value.get(field)))
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>();

    Table { headers, rows }
}

#[allow(clippy::unnecessary_result_map_or_else)]
fn stringify_json_value(value: Option<&Value>) -> String {
    let Some(value) = value else {
        return String::new();
    };
    match value {
        Value::Null => String::new(),
        Value::Bool(boolean) => boolean.to_string(),
        Value::Number(number) => number.to_string(),
        Value::String(text) => text.clone(),
        Value::Array(items) if items.iter().all(is_scalar) => items
            .iter()
            .map(|item| stringify_json_value(Some(item)))
            .collect::<Vec<_>>()
            .join(","),
        other => serde_json::to_string(other)
            .map_or_else(|_| json!(other).to_string(), |serialized| serialized),
    }
}

const fn is_scalar(value: &Value) -> bool {
    matches!(
        value,
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_)
    )
}

fn render_table(table: &Table, args: &Args) -> Result<String> {
    let mut widths = initial_widths(table, args)?;
    let mut visible_headers = table.headers.clone();
    let mut visible_rows = table.rows.clone();
    let mut omitted = Vec::new();

    if args.max_width > 0 && matches!(args.fit_mode, FitMode::DropLastThenShrink) {
        while total_width(&widths) > args.max_width && visible_headers.len() > args.min_columns {
            if let Some(header) = visible_headers.pop() {
                omitted.push(header);
                widths.pop();
                for row in &mut visible_rows {
                    row.pop();
                }
            } else {
                break;
            }
        }
    }

    if args.max_width > 0 {
        shrink_widths(&mut widths, args.max_width, args.min_col_width);
    }

    if visible_rows.is_empty() {
        return Ok(String::new());
    }

    let mut out = String::new();
    if !omitted.is_empty() {
        let _ = writeln!(out, "Columns omitted to fit width: {}", omitted.join(", "));
    }

    out.push_str(&border_line(&widths, '┌', '┬', '┐'));
    out.push('\n');
    out.push_str(&render_row(&visible_headers, &widths));
    out.push('\n');
    out.push_str(&border_line(&widths, '├', '┼', '┤'));
    out.push('\n');

    for (index, row) in visible_rows.iter().enumerate() {
        let wrapped = wrap_row(row, &widths);
        for line in wrapped {
            out.push_str(&render_row(&line, &widths));
            out.push('\n');
        }
        if index + 1 != visible_rows.len() {
            out.push_str(&border_line(&widths, '├', '┼', '┤'));
            out.push('\n');
        }
    }

    out.push_str(&border_line(&widths, '└', '┴', '┘'));
    out.push('\n');
    Ok(out)
}

fn initial_widths(table: &Table, args: &Args) -> Result<Vec<usize>> {
    let specified = parse_width_overrides(args.col_widths.as_deref(), table.headers.len())?;
    let mut widths = Vec::with_capacity(table.headers.len());
    for (index, header) in table.headers.iter().enumerate() {
        if let Some(width) = specified.get(index).and_then(|value| *value) {
            widths.push(width);
            continue;
        }
        let mut width = display_width(header);
        for row in &table.rows {
            let Some(cell) = row.get(index) else {
                bail!("render-table: row width mismatch at column {index}");
            };
            width = max(width, display_width(cell));
        }
        if args.max_col_width > 0 {
            width = min(width, args.max_col_width);
        }
        widths.push(max(width, 1));
    }
    Ok(widths)
}

fn parse_width_overrides(raw: Option<&str>, cols: usize) -> Result<Vec<Option<usize>>> {
    let mut result = vec![None; cols];
    let Some(raw) = raw else { return Ok(result) };
    for (index, part) in raw.split(',').enumerate() {
        if index >= cols {
            break;
        }
        let trimmed = part.trim();
        if trimmed.is_empty() {
            continue;
        }
        let Some(slot) = result.get_mut(index) else {
            break;
        };
        *slot = Some(trimmed.parse::<usize>().context("parse col-widths")?);
    }
    Ok(result)
}

fn total_width(widths: &[usize]) -> usize {
    widths.iter().sum::<usize>() + (widths.len() * 3) + 1
}

fn shrink_widths(widths: &mut [usize], max_width: usize, min_width: usize) {
    if max_width == 0 {
        return;
    }
    let minimum = max(min_width, 1);
    while total_width(widths) > max_width {
        let mut shrunk = false;
        for index in (0..widths.len()).rev() {
            if let Some(width) = widths.get_mut(index) {
                if *width > minimum {
                    *width -= 1;
                    shrunk = true;
                    if total_width(widths) <= max_width {
                        return;
                    }
                }
            }
        }
        if !shrunk {
            break;
        }
    }
}

fn border_line(widths: &[usize], left: char, middle: char, right: char) -> String {
    let mut line = String::new();
    line.push(left);
    for (index, width) in widths.iter().enumerate() {
        line.push_str(&"─".repeat(*width + 2));
        line.push(if index + 1 == widths.len() {
            right
        } else {
            middle
        });
    }
    line
}

fn render_row(cells: &[String], widths: &[usize]) -> String {
    let mut line = String::new();
    line.push('│');
    for (cell, width) in cells.iter().zip(widths) {
        let visible = truncate_display(cell, *width);
        let pad = width.saturating_sub(display_width(&visible));
        line.push(' ');
        line.push_str(&visible);
        line.push_str(&" ".repeat(pad));
        line.push(' ');
        line.push('│');
    }
    line
}

#[allow(clippy::manual_unwrap_or_default, clippy::option_if_let_else)]
fn wrap_row(row: &[String], widths: &[usize]) -> Vec<Vec<String>> {
    let wrapped = row
        .iter()
        .zip(widths)
        .map(|(cell, width)| wrap_cell(cell, *width))
        .collect::<Vec<_>>();
    let height = wrapped.iter().map(Vec::len).max().map_or(1, |value| value);
    (0..height)
        .map(|line_index| {
            wrapped
                .iter()
                .map(|lines| match lines.get(line_index).cloned() {
                    Some(value) => value,
                    None => String::new(),
                })
                .collect::<Vec<_>>()
        })
        .collect()
}

fn wrap_cell(cell: &str, width: usize) -> Vec<String> {
    if width == 0 {
        return vec![String::new()];
    }
    let mut lines = Vec::new();
    for raw_line in cell.replace('\r', "").split('\n') {
        let mut current = String::new();
        for word in raw_line.split_whitespace() {
            let tentative = if current.is_empty() {
                word.to_string()
            } else {
                format!("{current} {word}")
            };
            if display_width(&tentative) <= width {
                current = tentative;
                continue;
            }
            if !current.is_empty() {
                lines.push(current);
                current = String::new();
            }
            if display_width(word) <= width {
                current = word.to_string();
            } else {
                for chunk in break_word(word, width) {
                    lines.push(chunk);
                }
            }
        }
        if !current.is_empty() {
            lines.push(current);
        } else if raw_line.is_empty() {
            lines.push(String::new());
        }
    }
    if lines.is_empty() {
        lines.push(String::new());
    }
    lines
}

fn break_word(word: &str, width: usize) -> Vec<String> {
    let mut parts = Vec::new();
    let mut current = String::new();
    for ch in word.chars() {
        let next = format!("{current}{ch}");
        if display_width(&next) > width && !current.is_empty() {
            parts.push(current);
            current = ch.to_string();
        } else {
            current.push(ch);
        }
    }
    if !current.is_empty() {
        parts.push(current);
    }
    parts
}

fn truncate_display(text: &str, width: usize) -> String {
    let mut out = String::new();
    let mut used = 0;
    for ch in text.chars() {
        let ch_width = UnicodeWidthChar::width(ch).map_or(0, |value| value);
        if used + ch_width > width {
            break;
        }
        used += ch_width;
        out.push(ch);
    }
    out
}

fn display_width(text: &str) -> usize {
    UnicodeWidthStr::width(text)
}
