//! Minimal Rust foundation used by the Python-authoritative Kolibri runtime.
//!
//! The crate is intentionally shadow-only in this release. It validates the
//! frozen wire contract, durable Home events and fenced task/actor traces; it
//! does not bind a production listener or mutate Python Control Plane state.

pub mod event_store;
pub mod events;
pub mod swarm;
pub mod task_runtime;
pub mod task_shadow;
pub mod v1;
pub mod wire;

pub use crate::event_store::*;
pub use crate::events::*;
pub use crate::swarm::*;
pub use crate::task_runtime::*;
pub use crate::task_shadow::*;
pub use crate::v1::*;
pub use crate::wire::*;
