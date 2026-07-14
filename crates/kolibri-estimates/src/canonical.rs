use crate::EstimateError;
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};

pub fn canonical_json_bytes<T: Serialize + ?Sized>(value: &T) -> Result<Vec<u8>, EstimateError> {
    let value =
        serde_json::to_value(value).map_err(|error| EstimateError::canonical(error.to_string()))?;
    let mut output = Vec::new();
    write_value(&value, &mut output)?;
    Ok(output)
}

pub fn canonical_sha256<T: Serialize + ?Sized>(value: &T) -> Result<String, EstimateError> {
    let bytes = canonical_json_bytes(value)?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn write_value(value: &Value, output: &mut Vec<u8>) -> Result<(), EstimateError> {
    match value {
        Value::Null => output.extend_from_slice(b"null"),
        Value::Bool(true) => output.extend_from_slice(b"true"),
        Value::Bool(false) => output.extend_from_slice(b"false"),
        Value::Number(number) => output.extend_from_slice(number.to_string().as_bytes()),
        Value::String(text) => {
            let encoded = serde_json::to_string(text)
                .map_err(|error| EstimateError::canonical(error.to_string()))?;
            output.extend_from_slice(encoded.as_bytes());
        }
        Value::Array(items) => {
            output.push(b'[');
            for (index, item) in items.iter().enumerate() {
                if index > 0 {
                    output.push(b',');
                }
                write_value(item, output)?;
            }
            output.push(b']');
        }
        Value::Object(entries) => {
            output.push(b'{');
            let mut entries: Vec<_> = entries.iter().collect();
            entries.sort_unstable_by_key(|(left, _)| *left);
            for (index, (key, item)) in entries.into_iter().enumerate() {
                if index > 0 {
                    output.push(b',');
                }
                let encoded_key = serde_json::to_string(key)
                    .map_err(|error| EstimateError::canonical(error.to_string()))?;
                output.extend_from_slice(encoded_key.as_bytes());
                output.push(b':');
                write_value(item, output)?;
            }
            output.push(b'}');
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{canonical_json_bytes, canonical_sha256};
    use serde_json::json;

    #[test]
    fn sorts_object_keys_without_reordering_arrays() {
        let value = json!({"b": ["2", "1"], "a": "x"});
        let bytes = canonical_json_bytes(&value).expect("canonical JSON");
        assert_eq!(bytes, br#"{"a":"x","b":["2","1"]}"#);
    }

    #[test]
    fn stable_hash_has_a_golden_value() {
        let value = json!({"b": ["2", "1"], "a": "x"});
        let digest = canonical_sha256(&value).expect("canonical SHA-256");
        assert_eq!(
            digest, "9b016aa0f1a1e5537b09c3cce2d0d6b4a08145df1dfb980c78e5c487d0f0aebb",
            "canonical serialization changed"
        );
    }
}
