plugins {
    id("com.android.application")
}

android {
    namespace = "com.rukoz.tvhome"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.rukoz.tvhome"
        minSdk = 25
        targetSdk = 37
        versionCode = 1
        versionName = "0.1"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    sourceSets {
        getByName("main") {
            assets.srcDirs("../../vizio_privacy/dashboard/static")
        }
    }
}

dependencies {
    implementation("androidx.webkit:webkit:1.14.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20180813")
}
