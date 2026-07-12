use serde::{de, Deserialize, Deserializer, Serialize, Serializer};
use std::fmt;
use thiserror::Error;

/// Numeric V1 marker retained inside the scheduler and other state machines.
/// Public durable records use the family-specific string constants below.
pub const V1_SCHEMA_VERSION: u32 = 1;
pub const EVENT_SCHEMA_VERSION: &str = "kolibri.event.v1";
pub const SWARM_PLAN_SCHEMA_VERSION: &str = "kolibri.swarm-plan.v1";
pub const ACTOR_SCHEMA_VERSION: &str = "kolibri.actor.v1";

pub const fn v1_schema_version() -> u32 {
    V1_SCHEMA_VERSION
}

fn serialize_schema_version<S>(
    version: &u32,
    canonical: &'static str,
    serializer: S,
) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    if *version != V1_SCHEMA_VERSION {
        return Err(serde::ser::Error::custom(format_args!(
            "unsupported schema version {version}; expected {canonical}"
        )));
    }
    serializer.serialize_str(canonical)
}

fn deserialize_schema_version<'de, D>(
    deserializer: D,
    canonical: &'static str,
) -> Result<u32, D::Error>
where
    D: Deserializer<'de>,
{
    struct SchemaVersionVisitor {
        canonical: &'static str,
    }

    impl de::Visitor<'_> for SchemaVersionVisitor {
        type Value = u32;

        fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
            write!(
                formatter,
                "schema version {:?} or legacy numeric version 1",
                self.canonical
            )
        }

        fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            if value == u64::from(V1_SCHEMA_VERSION) {
                Ok(V1_SCHEMA_VERSION)
            } else {
                Err(E::invalid_value(de::Unexpected::Unsigned(value), &self))
            }
        }

        fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            if value == i64::from(V1_SCHEMA_VERSION) {
                Ok(V1_SCHEMA_VERSION)
            } else {
                Err(E::invalid_value(de::Unexpected::Signed(value), &self))
            }
        }

        fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            if value == self.canonical {
                Ok(V1_SCHEMA_VERSION)
            } else {
                Err(E::invalid_value(de::Unexpected::Str(value), &self))
            }
        }

        fn visit_string<E>(self, value: String) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            self.visit_str(&value)
        }
    }

    deserializer.deserialize_any(SchemaVersionVisitor { canonical })
}

macro_rules! schema_version_serde_module {
    ($module:ident, $canonical:ident) => {
        pub mod $module {
            use super::*;

            pub fn serialize<S>(version: &u32, serializer: S) -> Result<S::Ok, S::Error>
            where
                S: Serializer,
            {
                serialize_schema_version(version, $canonical, serializer)
            }

            pub fn deserialize<'de, D>(deserializer: D) -> Result<u32, D::Error>
            where
                D: Deserializer<'de>,
            {
                deserialize_schema_version(deserializer, $canonical)
            }
        }
    };
}

schema_version_serde_module!(event_schema_version, EVENT_SCHEMA_VERSION);

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct WireMetadata {
    #[serde(default = "v1_schema_version")]
    pub schema_version: u32,
    #[serde(default)]
    pub trace_id: String,
    #[serde(default)]
    pub idempotency_key: String,
}

impl WireMetadata {
    pub fn v1(trace_id: impl Into<String>, idempotency_key: impl Into<String>) -> Self {
        Self {
            schema_version: V1_SCHEMA_VERSION,
            trace_id: trace_id.into(),
            idempotency_key: idempotency_key.into(),
        }
    }

    pub fn validate(&self) -> Result<(), WireMetadataError> {
        if self.schema_version != V1_SCHEMA_VERSION {
            return Err(WireMetadataError::UnsupportedSchemaVersion(
                self.schema_version,
            ));
        }
        if self.trace_id.trim().is_empty() {
            return Err(WireMetadataError::MissingTraceId);
        }
        if self.idempotency_key.trim().is_empty() {
            return Err(WireMetadataError::MissingIdempotencyKey);
        }
        Ok(())
    }
}

impl Default for WireMetadata {
    fn default() -> Self {
        Self {
            schema_version: V1_SCHEMA_VERSION,
            trace_id: String::new(),
            idempotency_key: String::new(),
        }
    }
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum WireMetadataError {
    #[error("unsupported wire schema version: {0}")]
    UnsupportedSchemaVersion(u32),
    #[error("wire record requires a trace id")]
    MissingTraceId,
    #[error("wire record requires an idempotency key")]
    MissingIdempotencyKey,
}
