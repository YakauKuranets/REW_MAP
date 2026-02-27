package com.mapv12.dutytracker

import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions

class NumberPlateAnalyzer(
    private val onTextFound: (String) -> Unit,
) : ImageAnalysis.Analyzer {

    private val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

    // Локальный шаблон номерного знака: А123ВС + регион (2-3 цифры) с пробелами/без пробелов
    // Примеры: A123BC77, A123BC 777
    private val numberPlateRegex = Regex("[A-ZА-Я]\\d{3}[A-ZА-Я]{2}\\s?\\d{2,3}")

    override fun analyze(imageProxy: ImageProxy) {
        val mediaImage = imageProxy.image
        if (mediaImage == null) {
            imageProxy.close()
            return
        }

        val inputImage = InputImage.fromMediaImage(mediaImage, imageProxy.imageInfo.rotationDegrees)

        recognizer.process(inputImage)
            .addOnSuccessListener { visionText ->
                val normalizedText = visionText.text
                    .uppercase()
                    .replace("\n", " ")
                    .replace("[^A-ZА-Я0-9 ]".toRegex(), " ")
                    .replace("\\s+".toRegex(), " ")
                    .trim()

                val match = numberPlateRegex.find(normalizedText)
                if (match != null) {
                    onTextFound(match.value.replace(" ", ""))
                }
            }
            .addOnCompleteListener {
                imageProxy.close()
            }
    }
}
