use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug)]
pub struct ServerInfo {
    pub node_id: String,
    pub canonical_name: String,
    pub tier: String,
    pub tier_ru: String,
    pub internal_ip: Option<String>,
    pub external_ip: Option<String>,
    pub lifecycle: String,
}

#[derive(Serialize, Deserialize, Debug)]
pub struct FleetStatus {
    pub servers: Vec<ServerInfo>,
    pub total: usize,
}

const FLEET_API: &str = "http://192.168.88.210:9102";

#[tauri::command]
pub async fn get_fleet_status() -> Result<FleetStatus, String> {
    let resp = reqwest::get(format!("{}/v1/fleet/classification", FLEET_API))
        .await
        .map_err(|e| e.to_string())?;
    let data: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;

    let servers_map = data["servers"].as_object().ok_or("no servers")?;
    let mut servers = Vec::new();
    for (_, v) in servers_map {
        servers.push(ServerInfo {
            node_id: v["node_id"].as_str().unwrap_or("").to_string(),
            canonical_name: v["canonical_name"].as_str().unwrap_or("").to_string(),
            tier: v["tier"].as_str().unwrap_or("").to_string(),
            tier_ru: v["tier_ru"].as_str().unwrap_or("").to_string(),
            internal_ip: v["internal_ip"].as_str().map(|s| s.to_string()),
            external_ip: v["external_ip"].as_str().map(|s| s.to_string()),
            lifecycle: v["lifecycle"].as_str().unwrap_or("").to_string(),
        });
    }

    Ok(FleetStatus { total: servers.len(), servers })
}

#[tauri::command]
pub async fn get_server_details(node_id: String) -> Result<ServerInfo, String> {
    let resp = reqwest::get(format!("{}/v1/fleet/servers/{}", FLEET_API, node_id))
        .await
        .map_err(|e| e.to_string())?;
    let v: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;

    Ok(ServerInfo {
        node_id: v["node_id"].as_str().unwrap_or("").to_string(),
        canonical_name: v["canonical_name"].as_str().unwrap_or("").to_string(),
        tier: v["tier"].as_str().unwrap_or("").to_string(),
        tier_ru: v["tier_ru"].as_str().unwrap_or("").to_string(),
        internal_ip: v["internal_ip"].as_str().map(|s| s.to_string()),
        external_ip: v["external_ip"].as_str().map(|s| s.to_string()),
        lifecycle: v["lifecycle"].as_str().unwrap_or("").to_string(),
    })
}
