use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use deadpool_redis::{redis::AsyncCommands as PoolAsyncCommands, Config as RedisPoolConfig, Pool, Runtime};
use redis::AsyncCommands as RedisAsyncCommands;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use thiserror::Error;
use tracing::{error, info, warn};

#[derive(Deserialize, Serialize, Debug)]
struct TelemetryPayload {
    user_id: String,
    lat: f64,
    lon: f64,
    accuracy_m: Option<f64>,
    unit_label: Option<String>,
}

#[derive(Serialize)]
struct WsMessage {
    event: String,
    data: TelemetryPayload,
}

#[derive(Clone)]
struct AppState {
    redis_pool: Pool,
    redis_client: redis::Client,
    node_token: Option<String>,
}

#[derive(Debug, Error)]
enum NodeError {
    #[error("Redis error: {0}")]
    RedisError(String),
    #[error("Unauthorized")]
    Unauthorized,
    #[error("Invalid payload: {0}")]
    InvalidPayload(String),
    #[error("Internal server error: {0}")]
    Internal(String),
}

impl IntoResponse for NodeError {
    fn into_response(self) -> Response {
        let (status, code, message) = match self {
            Self::RedisError(msg) => (StatusCode::INTERNAL_SERVER_ERROR, "redis_error", msg),
            Self::Unauthorized => (
                StatusCode::UNAUTHORIZED,
                "unauthorized",
                "Unauthorized".to_string(),
            ),
            Self::InvalidPayload(msg) => (StatusCode::BAD_REQUEST, "invalid_payload", msg),
            Self::Internal(msg) => (
                StatusCode::INTERNAL_SERVER_ERROR,
                "internal_error",
                msg,
            ),
        };

        let body = Json(serde_json::json!({
            "error": code,
            "message": message,
        }));

        (status, body).into_response()
    }
}

fn authorize(headers: &HeaderMap, expected_token: Option<&str>) -> Result<(), NodeError> {
    let Some(expected) = expected_token else {
        return Ok(());
    };

    let provided = headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .map(str::trim)
        .or_else(|| {
            headers
                .get("x-node-token")
                .and_then(|v| v.to_str().ok())
                .map(str::trim)
        });

    match provided {
        Some(token) if token == expected => Ok(()),
        _ => Err(NodeError::Unauthorized),
    }
}

async fn handle_telemetry(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Json(payload): Json<TelemetryPayload>,
) -> Result<impl IntoResponse, NodeError> {
    authorize(&headers, state.node_token.as_deref())?;

    if !payload.lat.is_finite() || !payload.lon.is_finite() {
        return Err(NodeError::InvalidPayload(
            "Coordinates must be finite numbers".to_string(),
        ));
    }
    if !(-90.0..=90.0).contains(&payload.lat) || !(-180.0..=180.0).contains(&payload.lon) {
        return Err(NodeError::InvalidPayload(
            "lat/lon out of range".to_string(),
        ));
    }

    let ws_msg = WsMessage {
        event: "AGENT_LOCATION_UPDATE".to_string(),
        data: payload,
    };

    let msg_str = serde_json::to_string(&ws_msg)
        .map_err(|e| NodeError::InvalidPayload(format!("serialization failed: {e}")))?;

    // Legacy channel for backward compatibility.
    let mut pooled_con = state
        .redis_pool
        .get()
        .await
        .map_err(|e| NodeError::RedisError(format!("pool get failed: {e}")))?;

    let publish_legacy: Result<usize, _> = pooled_con.publish("map_updates", &msg_str).await;
    publish_legacy.map_err(|e| NodeError::RedisError(format!("publish to map_updates failed: {e}")))?;

    // High-frequency realtime bus consumed by Python websocket broker.
    let mut realtime_con = state
        .redis_client
        .get_async_connection()
        .await
        .map_err(|e| NodeError::RedisError(format!("redis async connection failed: {e}")))?;

    let publish_realtime: Result<usize, _> = realtime_con.publish("realtime_events", &msg_str).await;
    publish_realtime.map_err(|e| NodeError::RedisError(format!("publish to realtime_events failed: {e}")))?;

    Ok((StatusCode::OK, "OK"))
}

#[tokio::main]
async fn main() -> Result<(), NodeError> {
    tracing_subscriber::fmt()
        .with_env_filter(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "info,telemetry_node=debug".to_string()),
        )
        .init();

    let redis_url = std::env::var("REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1/".to_string());
    let node_token = std::env::var("NODE_TOKEN").ok().filter(|v| !v.trim().is_empty());

    let redis_client = redis::Client::open(redis_url.clone())
        .map_err(|e| NodeError::Internal(format!("redis client init failed: {e}")))?;

    let mut cfg = RedisPoolConfig::from_url(redis_url);
    cfg.pool = Some(deadpool_redis::PoolConfig::new(32));

    let pool = cfg
        .create_pool(Some(Runtime::Tokio1))
        .map_err(|e| NodeError::Internal(format!("redis pool init failed: {e}")))?;

    let state = Arc::new(AppState {
        redis_pool: pool,
        redis_client,
        node_token,
    });

    let app = Router::new()
        .route("/api/duty/telemetry/fast", post(handle_telemetry))
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000")
        .await
        .map_err(|e| NodeError::Internal(format!("bind failed: {e}")))?;

    info!("Rust Telemetry Node started on 0.0.0.0:3000");

    let serve_result = axum::serve(listener, app).await;
    if let Err(e) = serve_result {
        error!(error = %e, "server error");
        return Err(NodeError::Internal(format!("server error: {e}")));
    }

    warn!("server stopped gracefully");
    Ok(())
}
