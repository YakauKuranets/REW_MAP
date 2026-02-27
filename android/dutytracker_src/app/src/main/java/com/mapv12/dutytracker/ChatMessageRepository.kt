package com.mapv12.dutytracker

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.first

/**
 * Repository для отправки сообщений chat2 с поддержкой outbox.
 *
 * Этот класс помещает сообщения в локальную базу данных со статусом "queued" и
 * пытается отправлять их при появлении сети. После успешной отправки статус
 * обновляется на "sent" и сохраняется присвоенный сервером messageId.
 *
 * В текущем MVP методы являются заглушками: они демонстрируют схему, но не
 * реализуют подписку на realtime-события и получение истории.
 */
class ChatMessageRepository(
    private val db: AppDatabase,
    private val api: ApiClient
) {
    private val ioScope = CoroutineScope(Dispatchers.IO)

    /**
     * Добавить сообщение в очередь (outbox). Клиент должен передавать
     * случайно сгенерированный clientMsgId для идемпотентности.
     */
    fun enqueue(channelId: String, text: String, kind: String = "text", clientMsgId: String) {
        val entity = ChatMessageEntity(
            channelId = channelId,
            clientMsgId = clientMsgId,
            text = text,
            kind = kind,
            status = "queued"
        )
        ioScope.launch {
            db.chatMessageDao().insert(entity)
        }
    }

    /**
     * Отправить все сообщения со статусом queued. Вызывается периодически или при
     * появлении соединения с сервером. В случае успеха обновляет статус на
     * "sent" и сохраняет messageId, полученный от сервера.
     */
    fun flushOutbox() {
        ioScope.launch {
            val queued = db.chatMessageDao().observeMessagesByStatus("queued").first()
            for (msg in queued) {
                try {
                    val resp = apiSendMessage(msg)
                    // resp ожидается как JSON с полем message_id
                    val messageId = resp?.optString("id", null)
                    msg.messageId = messageId
                    msg.status = "sent"
                    db.chatMessageDao().update(msg)
                } catch (e: Exception) {
                    // leave as queued
                }
            }
        }
    }

    /**
     * Вызов отправки сообщения на сервер. Используется внутренне для
     * удаления дублирования. Возвращает JSONObject с данными о сообщении
     * (или null при ошибке).
     */
    private suspend fun apiSendMessage(msg: ChatMessageEntity): org.json.JSONObject? {
        return try {
            // Используем метод chatSend из ApiClient для отправки сообщения от устройства
            api.chatSend(
                channelId = msg.channelId,
                text = msg.text,
                kind = msg.kind ?: "text",
                clientMsgId = msg.clientMsgId ?: java.util.UUID.randomUUID().toString()
            )
        } catch (e: Exception) {
            null
        }
    }
}