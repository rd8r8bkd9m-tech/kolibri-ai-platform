use kolibri_response_core::{CoreSettings, build_router, parse_loopback_bind};
use kolibri_store_postgres::PostgresResponseRepository;
use sqlx::postgres::PgPoolOptions;
use std::{env, process::ExitCode};

#[tokio::main]
async fn main() -> ExitCode {
    match run().await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("kolibri-response-core: {error}");
            ExitCode::FAILURE
        }
    }
}

async fn run() -> Result<(), Box<dyn std::error::Error>> {
    let database_url = env::var("DATABASE_URL").map_err(|_| "DATABASE_URL is required")?;
    let bind_value = env::var("KOLIBRI_RESPONSE_CORE_BIND").ok();
    let bind = parse_loopback_bind(bind_value.as_deref())?;

    let pool = PgPoolOptions::new()
        .max_connections(16)
        .connect(&database_url)
        .await
        .map_err(|_| "failed to connect to PostgreSQL")?;
    let repository = PostgresResponseRepository::new(pool.clone());
    if env::var("KOLIBRI_RESPONSE_CORE_RUN_MIGRATIONS").as_deref() == Ok("1") {
        repository
            .migrate()
            .await
            .map_err(|_| "failed to apply response-core migrations")?;
    }

    let router = build_router(pool, CoreSettings::default())?;
    let listener = tokio::net::TcpListener::bind(bind).await?;
    let address = listener.local_addr()?;
    eprintln!(
        "kolibri-response-core listening on {address}; authority=control-plane/home persistence=postgresql"
    );
    axum::serve(listener, router).await?;
    Ok(())
}
