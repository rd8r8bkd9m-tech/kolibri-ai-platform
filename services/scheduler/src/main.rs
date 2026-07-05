use tokio::time::{sleep, Duration};

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();
    tracing::info!("scheduler started (MVP placeholder)");
    loop {
        tracing::debug!("watching for task.created events");
        sleep(Duration::from_secs(5)).await;
    }
}
