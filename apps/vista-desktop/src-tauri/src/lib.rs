use serde::Serialize;
use vista_core::{WorkspaceCommand, WorkspaceState, WorkspaceTransition};
use vista_policy::RoleId;

#[derive(Serialize)]
struct RuntimeInfo {
    product: &'static str,
    shell: &'static str,
    version: &'static str,
    os: String,
    arch: String,
}

#[tauri::command]
fn runtime_info() -> RuntimeInfo {
    RuntimeInfo {
        product: "Vista OS",
        shell: "tauri-desktop",
        version: env!("CARGO_PKG_VERSION"),
        os: std::env::consts::OS.to_string(),
        arch: std::env::consts::ARCH.to_string(),
    }
}

#[tauri::command]
fn allowed_apps(role: String) -> Vec<String> {
    RoleId::parse(&role).allowed_apps().iter().map(|value| value.to_string()).collect()
}

#[tauri::command]
fn apply_workspace_command(state: WorkspaceState, command: WorkspaceCommand) -> WorkspaceTransition {
    state.apply(command)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![runtime_info, allowed_apps, apply_workspace_command])
        .run(tauri::generate_context!())
        .expect("failed to run Vista OS desktop shell");
}
