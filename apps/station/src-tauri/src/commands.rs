#[tauri::command]
pub fn get_station_state() -> &'static str {
    "ready"
}
