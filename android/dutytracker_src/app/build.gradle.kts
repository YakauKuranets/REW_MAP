plugins {
    id("com.android.application") version "8.6.0" apply false
    id("com.android.library") version "8.6.0" apply false
    id("org.jetbrains.kotlin.android") version "2.0.21" apply false
    id("com.google.devtools.ksp") version "2.0.21-1.0.28" apply false
}


dependencies {
    // SQLCipher для шифрования Room (AES-256)
    implementation("net.zetetic:android-database-sqlcipher:4.5.4")
    implementation("androidx.sqlite:sqlite-framework:2.4.0")
    // Библиотека для общения с LoRa UART/USB платами
    implementation("com.github.mik3y:usb-serial-for-android:3.4.6")
    implementation("androidx.biometric:biometric:1.2.0-alpha05")
}


android {
    defaultConfig {
        ndk {
            abiFilters.addAll(listOf("armeabi-v7a", "arm64-v8a", "x86", "x86_64", "riscv64"))
        }
    }
}
