mod fleet_manager;
mod mimo_core;

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            fleet_manager::get_fleet_status,
            fleet_manager::get_server_details,
            mimo_core::chat,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
