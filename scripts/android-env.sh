# Source this file (do not run it): source scripts/android-env.sh
# Selects the JDK 17 and Android SDK installed under /Volumes/Storage/paperclip/toolchains/.

_android_toolchains="/Volumes/Storage/paperclip/toolchains"

if [ ! -x "$_android_toolchains/jdk-17/Contents/Home/bin/java" ]; then
  echo "android-env.sh: JDK 17 not found at $_android_toolchains/jdk-17/Contents/Home" >&2
  return 1
fi
if [ ! -x "$_android_toolchains/android-sdk/cmdline-tools/latest/bin/sdkmanager" ]; then
  echo "android-env.sh: Android SDK not found at $_android_toolchains/android-sdk (missing cmdline-tools/latest/bin/sdkmanager)" >&2
  return 1
fi

export JAVA_HOME="$_android_toolchains/jdk-17/Contents/Home"
export ANDROID_HOME="$_android_toolchains/android-sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export GRADLE_USER_HOME="$_android_toolchains/gradle-home"
# AVDs and adb/emulator settings stay on Storage, not in the real ~/.android (avdmanager uses Java user.home).
export ANDROID_USER_HOME="$_android_toolchains/android-user"
export ANDROID_AVD_HOME="$ANDROID_USER_HOME/avd"
mkdir -p "$ANDROID_AVD_HOME"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"

unset _android_toolchains
