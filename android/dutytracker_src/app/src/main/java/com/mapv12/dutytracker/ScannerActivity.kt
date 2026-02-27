package com.mapv12.dutytracker

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.TypedValue
import android.view.HapticFeedbackConstants
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class ScannerActivity : ComponentActivity() {

    private lateinit var viewFinder: PreviewView
    private lateinit var recognizedTextView: TextView
    private lateinit var cameraExecutor: ExecutorService

    private var lastPlate: String? = null
    private var lastPlateAt: Long = 0L

    private val requestCameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            startCamera()
        } else {
            Toast.makeText(this, "Нужно разрешение на камеру", Toast.LENGTH_LONG).show()
            finish()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_scanner)

        viewFinder = findViewById(R.id.viewFinder)
        recognizedTextView = findViewById(R.id.tvRecognizedText)
        val closeButton: MaterialButton = findViewById(R.id.btnCloseScanner)
        closeButton.setOnClickListener { finish() }

        recognizedTextView.setTextColor(ContextCompat.getColor(this, android.R.color.holo_green_light))
        recognizedTextView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 28f)

        cameraExecutor = Executors.newSingleThreadExecutor()

        if (hasCameraPermission()) {
            startCamera()
        } else {
            requestCameraPermission.launch(Manifest.permission.CAMERA)
        }
    }

    private fun hasCameraPermission(): Boolean {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)

        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder().build().also {
                it.surfaceProvider = viewFinder.surfaceProvider
            }

            val analyzer = NumberPlateAnalyzer { plate ->
                val now = System.currentTimeMillis()
                val isDuplicate = (lastPlate == plate) && (now - lastPlateAt < 1500)
                if (isDuplicate) return@NumberPlateAnalyzer

                lastPlate = plate
                lastPlateAt = now

                runOnUiThread {
                    recognizedTextView.text = plate
                    recognizedTextView.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
                }

                saveScanToJournal(plate)
            }

            val imageAnalysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also {
                    it.setAnalyzer(cameraExecutor, analyzer)
                }

            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(
                    this,
                    CameraSelector.DEFAULT_BACK_CAMERA,
                    preview,
                    imageAnalysis,
                )
            } catch (e: Exception) {
                Toast.makeText(this, "Ошибка запуска камеры: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun saveScanToJournal(plate: String) {
        val (lat, lon) = StatusStore.getLastLatLon(this) ?: (0.0 to 0.0)
        val extra = "plate=$plate,lat=$lat,lon=$lon"

        lifecycleScope.launch(Dispatchers.IO) {
            try {
                App.db.eventJournalDao().insert(
                    EventJournalEntity(
                        tsEpochMs = System.currentTimeMillis(),
                        kind = "scan_plate",
                        endpoint = "/local/scanner",
                        ok = true,
                        statusCode = null,
                        message = "number_plate_detected",
                        extra = extra,
                    ),
                )
            } catch (_: Exception) {
                // optional persistence: best-effort
            }
        }
    }

    override fun onDestroy() {
        cameraExecutor.shutdown()
        super.onDestroy()
    }
}
