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
}
