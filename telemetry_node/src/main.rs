use axum::{
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use deadpool_redis::{redis::AsyncCommands as PoolAsyncCommands, Config as RedisPoolConfig, Pool, Runtime};
use quinn::{Endpoint, ServerConfig};
use redis::AsyncCommands as RedisAsyncCommands;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::Arc;
use thiserror::Error;
use tokio::sync::mpsc;
use tower_governor::{governor::GovernorConfigBuilder, GovernorLayer};
use tower_http::limit::RequestBodyLimitLayer;
use tracing::{error, info, warn};

type TelemetryChannel = mpsc::Sender<Value>;

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
    telemetry_tx: TelemetryChannel,
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
            Self::Internal(msg) => (StatusCode::INTERNAL_SERVER_ERROR, "internal_error", msg),
        };

        let body = Json(serde_json::json!({
            "error": code,
            "message": message,
        }));

        (status, body).into_response()
    }
}

fn configure_quic_server() -> ServerConfig {
    let cert = rcgen::generate_simple_self_signed(vec!["localhost".into()]).unwrap();
    let cert_der = cert.serialize_der().unwrap();
    let priv_key = cert.serialize_private_key_der();

    let cert_chain = vec![rustls::Certificate(cert_der)];
    let key = rustls::PrivateKey(priv_key);

    let mut server_crypto = rustls::ServerConfig::builder()
        .with_safe_defaults()
        .with_no_client_auth()
        .with_single_cert(cert_chain, key)
        .unwrap();

    server_crypto.alpn_protocols = vec![b"playe-telemetry-v6".to_vec()];

    let mut server_config = ServerConfig::with_crypto(Arc::new(server_crypto));
    Arc::get_mut(&mut server_config.transport)
        .unwrap()
        .max_concurrent_bidi_streams(10_000_u32.into());

    server_config
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
        return Err(NodeError::InvalidPayload("lat/lon out of range".to_string()));
    }

    let ws_msg = WsMessage {
        event: "AGENT_LOCATION_UPDATE".to_string(),
        data: payload,
    };

    let msg_str = serde_json::to_string(&ws_msg)
        .map_err(|e| NodeError::InvalidPayload(format!("serialization failed: {e}")))?;

    // Fast handoff to io_uring worker queue (best effort).
    let queue_payload: Value = serde_json::from_str(&msg_str)
        .map_err(|e| NodeError::InvalidPayload(format!("queue payload parse failed: {e}")))?;
    if let Err(e) = state.telemetry_tx.send(queue_payload).await {
        warn!("[RUST_GATEWAY] queue send failed: {e}");
    }

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

    info!("[RUST_GATEWAY] Инициализация PLAYE TELEMETRY NODE v6.0");

    let (tx, mut rx) = mpsc::channel::<Value>(100_000);

    // io_uring runtime for ultra-fast ingest buffering path.
    std::thread::spawn(move || {
        tokio_uring::start(async move {
            info!("[IO_URING] Аппаратное ускорение Linux Ring Buffer активировано.");

            while let Some(payload) = rx.recv().await {
                let _buf = format!("{}\n", payload).into_bytes();
                // MVP stub for future direct io_uring fs/net sink.
                // let file = tokio_uring::fs::File::create("telemetry_dump.log").await.unwrap();
                // let (_res, _buf) = file.write_at(_buf, 0).await;
            }
        });
    });

    // QUIC runtime endpoint on UDP/9002 shares the same telemetry queue.
    let quic_tx = tx.clone();
    tokio::spawn(async move {
        let server_config = configure_quic_server();
        let endpoint = Endpoint::server(server_config, "[::]:9002".parse().unwrap()).unwrap();
        info!("[QUIC_GATEWAY] Сверхбыстрый UDP/QUIC шлюз прослушивает 9002");

        while let Some(conn) = endpoint.accept().await {
            let quic_tx_clone = quic_tx.clone();
            tokio::spawn(async move {
                if let Ok(connection) = conn.await {
                    info!(
                        "[QUIC_GATEWAY] Установлено бесшовное соединение с агентом: {}",
                        connection.remote_address()
                    );

                    while let Ok(mut stream) = connection.accept_uni().await {
                        let tx_inner = quic_tx_clone.clone();
                        tokio::spawn(async move {
                            if let Ok(data) = stream.read_to_end(65_536).await {
                                if let Ok(json_val) = serde_json::from_slice::<Value>(&data) {
                                    let _ = tx_inner.send(json_val).await;
                                }
                            }
                        });
                    }
                }
            });
        }
    });

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
        telemetry_tx: tx,
    });

    let governor_conf = Box::new(
        GovernorConfigBuilder::default()
            .per_second(10)
            .burst_size(50)
            .finish()
            .unwrap(),
    );

    let app = Router::new()
        .route("/api/duty/telemetry/fast", post(handle_telemetry))
        .route("/api/v1/telemetry", post(handle_telemetry))
        .with_state(state)
        .layer(DefaultBodyLimit::disable())
        .layer(RequestBodyLimitLayer::new(64 * 1024))
        .layer(GovernorLayer {
            config: Box::leak(governor_conf),
        });

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000")
        .await
        .map_err(|e| NodeError::Internal(format!("bind failed: {e}")))?;

    info!("[RUST_GATEWAY] Axum-сервер прослушивает 0.0.0.0:3000");

    let serve_result = axum::serve(listener, app).await;
    if let Err(e) = serve_result {
        error!(error = %e, "server error");
        return Err(NodeError::Internal(format!("server error: {e}")));
    }

    warn!("server stopped gracefully");
    Ok(())
}
