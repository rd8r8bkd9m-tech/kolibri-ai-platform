use tauri::command;

#[command]
fn station_health() -> &'static str {
    "ok"
}

mod commands;

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![station_health, commands::get_station_state])
        .run(tauri::generate_context!())
        .expect("error while running tauri app");
}
