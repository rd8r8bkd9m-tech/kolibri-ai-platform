use serde_json::Value;

pub fn requires_approval(kind: &str, sensitivity: &str, policy: &Value) -> bool {
    if policy
        .get("approval_required")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        return true;
    }

    if matches!(
        sensitivity.to_lowercase().as_str(),
        "sensitive" | "private" | "confidential"
    ) {
        return true;
    }

    matches!(
        kind.to_lowercase().as_str(),
        "deploy" | "publish" | "prod-deploy" | "secret-rotate"
    )
}

#[cfg(test)]
mod tests {
    use super::requires_approval;
    use serde_json::json;

    #[test]
    fn policy_flag_requires_approval() {
        let policy = json!({ "approval_required": true });
        assert!(requires_approval("test", "public", &policy));
    }

    #[test]
    fn sensitive_data_requires_approval() {
        assert!(requires_approval("test", "private", &json!({})));
        assert!(requires_approval("test", "confidential", &json!({})));
    }

    #[test]
    fn dangerous_kind_requires_approval() {
        assert!(requires_approval("deploy", "public", &json!({})));
        assert!(requires_approval("publish", "public", &json!({})));
        assert!(requires_approval("prod-deploy", "public", &json!({})));
    }
}
