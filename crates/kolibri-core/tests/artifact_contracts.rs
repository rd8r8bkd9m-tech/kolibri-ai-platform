use chrono::{DateTime, Utc};
use kolibri_core::{
    Artifact, ArtifactKind, ArtifactRecord, BrowserNetworkPolicy, BrowserSession,
    BrowserSessionStatus, CanvasArtifact, CanvasKind, PluginSignature, PreviewRuntime,
    PreviewRuntimeKind, PreviewRuntimeStatus, RendererPlugin, RuntimeQuota,
};
use serde_json::json;
use uuid::Uuid;

fn at(seconds: i64) -> DateTime<Utc> {
    DateTime::from_timestamp(seconds, 0).expect("valid fixture timestamp")
}

#[test]
fn legacy_artifact_json_remains_deserializable() {
    let raw = json!({
        "id": Uuid::new_v4(),
        "task_run_id": null,
        "task_id": null,
        "artifact_type": "test_report",
        "name": "report.json",
        "path": "artifacts/report.json",
        "sha256": "sha256:fixture",
        "size_bytes": 42,
        "metadata_json": {},
        "created_at": at(1),
    });
    let artifact: Artifact = serde_json::from_value(raw).expect("legacy artifact contract");
    assert_eq!(artifact.artifact_type, "test_report");
    assert_eq!(artifact.path, "artifacts/report.json");

    let record = ArtifactRecord {
        artifact,
        schema_version: 1,
        trace_id: "trace:artifact-record".into(),
        idempotency_key: "artifact-record:fixture".into(),
        tenant_id: Uuid::new_v4(),
        project_id: Uuid::new_v4(),
        workstream_id: None,
        execution_id: None,
        kind: ArtifactKind::TestReport,
        mime_type: "application/json".into(),
        storage_ref: "sha256:fixture".into(),
        sensitivity: "internal".into(),
        retention_class: "project".into(),
        provenance_json: json!({"verified":true}),
        lineage: vec![],
    };
    assert_eq!(record.schema_version, 1);
}

#[test]
fn renderer_preview_and_browser_contracts_are_sandbox_bound() {
    let artifact_id = Uuid::new_v4();
    let canvas = CanvasArtifact {
        id: Uuid::new_v4(),
        artifact_id,
        schema_version: 1,
        trace_id: "trace:canvas".into(),
        idempotency_key: "canvas:fixture".into(),
        kind: CanvasKind::WebApp,
        document_tree: json!({"type":"page","children":[]}),
        data_bindings: json!({}),
        asset_artifact_ids: vec![],
        render_hints: json!({"responsive":true}),
        created_at: at(1),
    };
    let renderer = RendererPlugin {
        id: "kolibri.web.renderer".into(),
        version: "1.0.0".into(),
        input_kinds: vec![CanvasKind::WebApp],
        output_artifact_kinds: vec![ArtifactKind::WebAppBundle],
        output_mime_types: vec!["application/vnd.kolibri.webapp+zip".into()],
        sandbox_profile: "renderer-wasi-default-deny".into(),
        deterministic: true,
        signature: PluginSignature {
            algorithm: "ed25519".into(),
            signer: "kolibri-release".into(),
            checksum_sha256: "sha256:renderer".into(),
            signature: "signature:fixture".into(),
        },
        enabled: true,
    };
    let preview = PreviewRuntime {
        schema_version: 1,
        trace_id: "trace:preview".into(),
        idempotency_key: "preview:fixture".into(),
        id: Uuid::new_v4(),
        project_id: Uuid::new_v4(),
        workstream_id: Uuid::new_v4(),
        source_artifact_id: artifact_id,
        runtime_kind: PreviewRuntimeKind::WebApp,
        status: PreviewRuntimeStatus::Ready,
        sandbox_profile: "preview-container-no-host-mounts".into(),
        quota: RuntimeQuota {
            cpu_millis: 500,
            memory_bytes: 256 * 1024 * 1024,
            disk_bytes: 1024 * 1024 * 1024,
            max_seconds: 900,
        },
        preview_url: Some("https://preview.invalid/session".into()),
        stream_id: Some("preview-stream".into()),
        evidence_artifact_ids: vec![],
        created_at: at(1),
        expires_at: at(901),
    };
    let browser = BrowserSession {
        schema_version: 1,
        trace_id: "trace:browser".into(),
        idempotency_key: "browser:fixture".into(),
        id: Uuid::new_v4(),
        preview_runtime_id: preview.id,
        status: BrowserSessionStatus::Ready,
        sandbox_profile: "browser-isolated".into(),
        network_policy: BrowserNetworkPolicy {
            allowed_origins: vec!["https://preview.invalid".into()],
            allowed_hosts: vec!["preview.invalid".into()],
            deny_private_networks: true,
            downloads_enabled: false,
        },
        stream_id: Some("browser-stream".into()),
        actions: vec![],
        evidence_artifact_ids: vec![],
        created_at: at(2),
        expires_at: at(902),
    };

    assert_eq!(canvas.kind, CanvasKind::WebApp);
    assert!(renderer.deterministic);
    assert!(renderer.sandbox_profile.contains("default-deny"));
    assert!(preview.stream_id.is_some());
    assert!(browser.network_policy.deny_private_networks);
    assert!(!browser.network_policy.downloads_enabled);
}
