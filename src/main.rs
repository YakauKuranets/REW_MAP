use axum::{extract::State, http::StatusCode, routing::post, Json, Router};
use axum_extra::TypedHeader;
use deadpool_redis::{redis::AsyncCommands, Config as RedisPoolConfig, Pool, Runtime};
use headers::{authorization::Bearer, Authorization};
use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

// Структура, которую присылает Android-приложение
#[derive(Deserialize, Serialize, Debug)]
struct TelemetryPayload {
    user_id: String,
    lat: f64,
    lon: f64,
    accuracy_m: Option<f64>,
    unit_label: Option<String>,
}

#[derive(Debug, Deserialize)]
struct JwtClaims {
    sub: Option<String>,
    exp: usize,
}

// Структура для отправки в нашу WebSocket-шину (чтобы React-карта поняла)
#[derive(Serialize)]
struct WsMessage {
    event: String,
    data: TelemetryPayload,
}

// Состояние приложения (держит пул подключений к Redis)
struct AppState {
    redis_pool: Pool,
    jwt_secret: String,
}

fn validate_bearer_token(token: &str, secret: &str) -> bool {
    let mut validation = Validation::new(Algorithm::HS256);
    validation.validate_exp = true;

    decode::<JwtClaims>(
        token,
        &DecodingKey::from_secret(secret.as_bytes()),
        &validation,
    )
    .is_ok()
}

// Сверхбыстрый эндпоинт приема координат
async fn handle_telemetry(
    State(state): State<Arc<AppState>>,
    TypedHeader(auth): TypedHeader<Authorization<Bearer>>,
    Json(payload): Json<TelemetryPayload>,
) -> Result<StatusCode, StatusCode> {
    // 0. Zero Trust: отбрасываем невалидный токен до любых действий с Redis
    if !validate_bearer_token(auth.token(), &state.jwt_secret) {
        return Err(StatusCode::UNAUTHORIZED);
    }

    // 1. Забираем коннект из пула
    let mut conn = state
        .redis_pool
        .get()
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    // 2. Упаковываем в нужный формат для фронтенда
    let ws_msg = WsMessage {
        event: "duty_location_update".to_string(), // Это событие ждет карта
        data: payload,
    };

    // 3. Сериализация Payload в JSON
    let msg_str = serde_json::to_string(&ws_msg).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    // 4. Асинхронный publish в Redis
    let _: usize = conn
        .publish("map_updates", msg_str)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    // 5. Возвращаем 200 OK
    Ok(StatusCode::OK)
}

#[tokio::main]
async fn main() {
    // Подключаемся к Redis (в продакшене брать из ENV)
    let redis_url = std::env::var("REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1/".to_string());

    // Секрет для проверки JWT подписи (обязателен для Zero Trust)
    let jwt_secret = std::env::var("NODE_JWT_SECRET")
        .expect("❌ NODE_JWT_SECRET is required for JWT validation");

    // Инициализируем пул (100 соединений)
    let mut cfg = RedisPoolConfig::from_url(redis_url);
    cfg.pool = Some(deadpool_redis::PoolConfig::new(100));

    let pool = cfg
        .create_pool(Some(Runtime::Tokio1))
        .expect("❌ Не удалось создать Redis pool");

    let state = Arc::new(AppState {
        redis_pool: pool,
        jwt_secret,
    });

    // Настраиваем роутер Axum
    let app = Router::new()
        .route("/api/duty/telemetry/fast", post(handle_telemetry))
        .with_state(state);

    // Запускаем сервер на порту 3000
    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();
    println!("🚀 Rust Telemetry Node запущена на порту 3000!");
    axum::serve(listener, app).await.unwrap();
}
