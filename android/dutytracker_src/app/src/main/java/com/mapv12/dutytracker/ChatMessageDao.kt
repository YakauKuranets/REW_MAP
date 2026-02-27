package com.mapv12.dutytracker

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface ChatMessageDao {
    @Query("SELECT * FROM chat_messages WHERE channelId = :channelId ORDER BY createdAt ASC")
    fun observeMessagesForChannel(channelId: String): Flow<List<ChatMessageEntity>>

    @Insert
    suspend fun insert(message: ChatMessageEntity): Long

    @Update
    suspend fun update(message: ChatMessageEntity)

    @Delete
    suspend fun delete(message: ChatMessageEntity)

    @Query("SELECT * FROM chat_messages WHERE status = :status ORDER BY createdAt ASC")
    fun observeMessagesByStatus(status: String): Flow<List<ChatMessageEntity>>
}
