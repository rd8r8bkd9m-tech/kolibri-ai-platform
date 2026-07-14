use estimate_engine::app;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let bind =
        std::env::var("ESTIMATE_ENGINE_BIND").unwrap_or_else(|_| "127.0.0.1:8090".to_owned());
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    axum::serve(listener, app()).await?;
    Ok(())
}
