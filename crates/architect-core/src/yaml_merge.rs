//! Shared YAML merge-key materialization helpers.

use serde_yaml::{Mapping, Value as YamlValue};

use crate::error::AppError;

pub(crate) const MAX_YAML_MERGE_DEPTH: u8 = 128;
const YAML_MERGE_KEY: &str = "<<";

/// Resolve YAML merge keys in-place using standard YAML precedence.
pub(crate) fn materialize_yaml_merge_keys(
    value: &mut YamlValue,
    depth_remaining: u8,
) -> Result<(), AppError> {
    if depth_remaining == 0 {
        return Err(AppError::InvalidInput {
            reason: "compose yaml nesting depth exceeded".to_string(),
        });
    }
    let next_depth = depth_remaining - 1;

    match value {
        YamlValue::Mapping(mapping) => {
            let merge_key = YamlValue::String(YAML_MERGE_KEY.to_string());
            let merge_value = mapping.remove(&merge_key);

            for child in mapping.values_mut() {
                materialize_yaml_merge_keys(child, next_depth)?;
            }

            let Some(mut merge_value) = merge_value else {
                return Ok(());
            };

            materialize_yaml_merge_keys(&mut merge_value, next_depth)?;
            let source_mappings = parse_yaml_merge_sources(merge_value)?;
            let mut merged = Mapping::new();

            // YAML merge precedence keeps earlier sequence entries authoritative.
            for source in source_mappings.into_iter().rev() {
                for (key, source_value) in source {
                    merged.insert(key, source_value);
                }
            }

            for (key, explicit_value) in std::mem::take(mapping) {
                merged.insert(key, explicit_value);
            }
            *mapping = merged;
            Ok(())
        }
        YamlValue::Sequence(items) => {
            for item in items {
                materialize_yaml_merge_keys(item, next_depth)?;
            }
            Ok(())
        }
        YamlValue::Tagged(tagged) => materialize_yaml_merge_keys(&mut tagged.value, next_depth),
        _ => Ok(()),
    }
}

fn parse_yaml_merge_sources(merge_value: YamlValue) -> Result<Vec<Mapping>, AppError> {
    match merge_value {
        YamlValue::Mapping(mapping) => Ok(vec![mapping]),
        YamlValue::Sequence(items) => {
            let mut mappings = Vec::new();
            for item in items {
                match item {
                    YamlValue::Mapping(mapping) => mappings.push(mapping),
                    _ => {
                        return Err(AppError::InvalidInput {
                            reason: "compose merge key `<<` must reference a mapping or sequence of mappings"
                                .to_string(),
                        });
                    }
                }
            }
            Ok(mappings)
        }
        _ => Err(AppError::InvalidInput {
            reason: "compose merge key `<<` must reference a mapping or sequence of mappings"
                .to_string(),
        }),
    }
}
