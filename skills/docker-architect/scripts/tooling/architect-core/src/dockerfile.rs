//! Deterministic Dockerfile parsing helpers used by policy evaluators.

use std::ops::Range;

use crate::error::AppError;

/// One parsed Dockerfile instruction.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DockerInstruction {
    /// Uppercase instruction keyword (for example `FROM` or `RUN`).
    pub keyword: String,
    /// Original instruction arguments (without keyword).
    pub arguments: String,
    /// Start line number in the source file (1-based).
    pub line: usize,
}

/// Parsed Dockerfile structure with deterministic stage ranges.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedDockerfile {
    instructions: Vec<DockerInstruction>,
    stages: Vec<Range<usize>>,
}

impl ParsedDockerfile {
    /// Parse Dockerfile text into instructions and stage ranges.
    ///
    /// # Arguments
    /// * `content` - Raw Dockerfile text.
    ///
    /// # Returns
    /// * `Ok(ParsedDockerfile)` with deterministic instruction ordering.
    /// * `Err(AppError)` when parsing cannot proceed.
    pub fn parse(content: &str) -> Result<Self, AppError> {
        let logical_lines = build_logical_lines(content)?;
        let mut instructions = Vec::new();
        for (line, text) in logical_lines {
            let trimmed = text.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                continue;
            }

            let mut parts = trimmed.splitn(2, char::is_whitespace);
            let Some(keyword) = parts.next() else {
                continue;
            };
            let arguments = parts.next().unwrap_or("").trim().to_string();
            instructions.push(DockerInstruction {
                keyword: keyword.to_ascii_uppercase(),
                arguments,
                line,
            });
        }

        let mut stage_starts = Vec::new();
        for (index, instruction) in instructions.iter().enumerate() {
            if instruction.keyword == "FROM" {
                stage_starts.push(index);
            }
        }

        let mut stages = Vec::new();
        for (idx, start) in stage_starts.iter().enumerate() {
            let end = stage_starts
                .get(idx + 1)
                .copied()
                .unwrap_or(instructions.len());
            stages.push(*start..end);
        }

        Ok(Self {
            instructions,
            stages,
        })
    }

    /// Return whether the Dockerfile contains multiple stages.
    pub fn has_multiple_stages(&self) -> bool {
        self.stages.len() >= 2
    }

    /// Return the final stage range.
    pub fn final_stage_range(&self) -> Option<Range<usize>> {
        self.stages.last().cloned()
    }

    /// Return a reference to all parsed instructions.
    pub fn instructions(&self) -> &[DockerInstruction] {
        &self.instructions
    }

    /// Return the first instruction in the final stage (`FROM` instruction).
    pub fn final_stage_from_instruction(&self) -> Option<&DockerInstruction> {
        let range = self.final_stage_range()?;
        self.instructions.get(range.start)
    }

    /// Return the last instruction in the final stage matching `keyword`.
    pub fn last_instruction_in_final_stage(&self, keyword: &str) -> Option<&DockerInstruction> {
        let range = self.final_stage_range()?;
        let expected = keyword.to_ascii_uppercase();
        self.instructions[range]
            .iter()
            .rfind(|instruction| instruction.keyword == expected)
    }

    /// Return final-stage instructions matching a specific keyword.
    pub fn final_stage_instructions_by_keyword(&self, keyword: &str) -> Vec<&DockerInstruction> {
        let Some(range) = self.final_stage_range() else {
            return Vec::new();
        };

        let expected = keyword.to_ascii_uppercase();
        self.instructions[range]
            .iter()
            .filter(|instruction| instruction.keyword == expected)
            .collect()
    }
}

fn build_logical_lines(content: &str) -> Result<Vec<(usize, String)>, AppError> {
    let mut output = Vec::new();
    let mut current = String::new();
    let mut start_line = 0usize;

    for (index, raw_line) in content.lines().enumerate() {
        let line_no = index + 1;
        let trimmed = raw_line.trim_end();

        if current.is_empty() {
            start_line = line_no;
        } else {
            current.push(' ');
        }
        current.push_str(trimmed.trim_start());

        if ends_with_unescaped_backslash(trimmed) {
            let _ = current.pop();
            continue;
        }

        output.push((start_line, current.trim().to_string()));
        current.clear();
    }

    if !current.trim().is_empty() {
        return Err(AppError::InvalidInput {
            reason: "dockerfile ended with trailing line continuation".to_string(),
        });
    }

    Ok(output)
}

fn ends_with_unescaped_backslash(value: &str) -> bool {
    let mut chars = value.chars().rev();
    matches!(chars.next(), Some('\\'))
}

#[cfg(test)]
mod tests {
    use super::ParsedDockerfile;

    #[test]
    fn parse_preserves_logical_lines_with_continuations() {
        let content = r#"
FROM debian:12
RUN apt-get update && \
    apt-get install -y curl
"#;
        let parsed = ParsedDockerfile::parse(content).expect("parse should succeed");
        let run = parsed
            .instructions()
            .iter()
            .find(|instruction| instruction.keyword == "RUN")
            .expect("run instruction should exist");
        assert!(run.arguments.contains("apt-get update"));
        assert!(run.arguments.contains("apt-get install -y curl"));
    }

    #[test]
    fn parse_detects_multiple_stages_and_final_stage() {
        let content = r#"
FROM rust:1.84 AS builder
RUN cargo build --release
FROM gcr.io/distroless/static:nonroot
COPY --from=builder /app /app
"#;
        let parsed = ParsedDockerfile::parse(content).expect("parse should succeed");
        assert!(parsed.has_multiple_stages());
        let from = parsed
            .final_stage_from_instruction()
            .expect("final stage from should exist");
        assert_eq!(from.keyword, "FROM");
        assert!(from.arguments.contains("distroless/static:nonroot"));
    }
}
