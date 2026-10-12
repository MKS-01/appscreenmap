plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "dev.appscreenmap.playground"
    compileSdk = 36

    defaultConfig {
        applicationId = "dev.appscreenmap.playground"
        minSdk = 26
        targetSdk = 36
    }

    // Two builds of the same app for the visual-diff / perf / a11y comparison demos.
    // Same applicationId, so v2 installs over v1 like a real update.
    flavorDimensions += "release"
    productFlavors {
        create("v1") {
            dimension = "release"
            versionCode = 1
            versionName = "1.0"
            buildConfigField("boolean", "V2", "false")
        }
        create("v2") {
            dimension = "release"
            versionCode = 2
            versionName = "2.0"
            buildConfigField("boolean", "V2", "true")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
            // A demo app: signed with the local debug key so anyone can build and install it.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.compose.ui:ui:1.11.1")
    implementation("androidx.compose.foundation:foundation:1.11.1")
    implementation("androidx.compose.material3:material3:1.4.0")
    implementation("androidx.compose.material:material-icons-core:1.7.6")
}
