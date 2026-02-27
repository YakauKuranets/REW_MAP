package com.mapv12.dutytracker

import android.os.Bundle
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.chip.ChipGroup
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class JournalActivity : AppCompatActivity() {

    private lateinit var adapter: JournalAdapter
    private lateinit var chips: ChipGroup
    private lateinit var tvEmpty: TextView
    private var all: List<EventJournalEntity> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_journal)

        // Toolbar
        val toolbar = findViewById<MaterialToolbar>(R.id.toolbar)
        setSupportActionBar(toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        toolbar.setNavigationOnClickListener { finish() }

        // RecyclerView с DiffUtil-адаптером
        adapter = JournalAdapter()
        tvEmpty = findViewById(R.id.tv_empty)

        findViewById<RecyclerView>(R.id.recycler_journal).apply {
            layoutManager = LinearLayoutManager(this@JournalActivity).also { it.reverseLayout = false }
            adapter = this@JournalActivity.adapter
        }

        // Фильтр по типу события
        chips = findViewById(R.id.chips)
        chips.setOnCheckedStateChangeListener { _, _ -> applyFilter() }

        load()
    }

    private fun load() {
        lifecycleScope.launch {
            all = withContext(Dispatchers.IO) {
                runCatching { App.db.eventJournalDao().last(500) }.getOrElse { emptyList() }
            }
            applyFilter()
        }
    }

    private fun applyFilter() {
        val checkedId = chips.checkedChipId
        val filtered = when (checkedId) {
            R.id.chip_upload   -> all.filter { it.kind.equals("upload",   true) }
            R.id.chip_gps      -> all.filter { it.kind.equals("gps",      true) }
            R.id.chip_err      -> all.filter { !it.ok }
            R.id.chip_watchdog -> all.filter { it.kind.equals("watchdog", true) }
            else               -> all
        }
        adapter.submitList(filtered)
        tvEmpty.visibility = if (filtered.isEmpty()) View.VISIBLE else View.GONE
    }
}
