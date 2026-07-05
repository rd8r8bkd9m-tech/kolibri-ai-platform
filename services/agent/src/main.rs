use clap::Parser;
use tracing::info;

#[derive(Debug, Parser)]
#[command(name = "kolibri-agent")]
struct AgentCli {
    #[arg(long, default_value = "http://127.0.0.1:8080")]
    control_plane: String,
}

#[tokio::main]
async fn main() {
    let cli = AgentCli::parse();
    tracing_subscriber::fmt::init();
    info!("agent booted, control-plane={}", cli.control_plane);
    info!("agent heartbeat loop placeholder started");
}
