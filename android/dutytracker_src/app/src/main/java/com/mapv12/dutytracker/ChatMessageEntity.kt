package com.mapv12.dutytracker

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Entity для хранения сообщений чат2 на устройстве.
 *
 * Держит локальную очередь (outbox) и кеш полученных сообщений. В первой версии
 * используются только базовые поля: channelId — идентификатор канала;
 * messageId — идентификатор сообщения, присвоенный сервером (может быть null
 * до подтверждения отправки);
 * clientMsgId — уникальный идентификатор, сгенерированный клиентом;
 * text/kind — текст и тип (text/template/media/command и т.д.);
 * status — queued/sent/delivered/read (для outbox);
 * createdAt — время создания (мс, локальное устройство).
 */
@Entity(tableName = "chat_messages")
data class ChatMessageEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val channelId: String,
    var messageId: String? = null,
    val clientMsgId: String? = null,
    val text: String? = null,
    val kind: String? = null,
    var status: String = "queued",
    val createdAt: Long = System.currentTimeMillis()
)