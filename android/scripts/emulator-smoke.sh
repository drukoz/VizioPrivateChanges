#!/bin/bash
# Smoke test on a headless emulator: install the debug APK, open TV Home, record what the page did.
# Usage: bash emulator-smoke.sh <avd-name> <even port 5554-5680> <output dir> <apk>
set -u
source "$(cd "$(dirname "$0")/../.." && pwd)/scripts/android-env.sh" || exit 1
AVD="$1"; PORT="$2"; OUT="$3"; APK="$4"
SERIAL="emulator-$PORT"
mkdir -p "$OUT"
cleanup() {
  adb -s "$SERIAL" emu kill >/dev/null 2>&1
  sleep 5
  avdmanager delete avd -n "$AVD" >/dev/null 2>&1
}
trap cleanup EXIT
echo no | avdmanager create avd -n "$AVD" -k "system-images;android-36;google_apis;arm64-v8a" -d tv_1080p --force >/dev/null || exit 1
emulator -avd "$AVD" -port "$PORT" -no-window -no-audio -no-snapshot -no-boot-anim -gpu swiftshader_indirect >"$OUT/emulator.log" 2>&1 &
adb -s "$SERIAL" wait-for-device
booted=0
for i in $(seq 1 90); do
  if [ "$(adb -s "$SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then booted=1; break; fi
  sleep 4
done
[ "$booted" = 1 ] || { echo "FAIL emulator did not boot"; exit 1; }
echo "booted after about $((i * 4)) s"
adb -s "$SERIAL" install -r "$APK" || { echo "FAIL install"; exit 1; }
adb -s "$SERIAL" logcat -c
adb -s "$SERIAL" shell am start -W -n com.rukoz.tvhome/.HomeActivity
sleep 15
adb -s "$SERIAL" exec-out screencap -p >"$OUT/home.png"
adb -s "$SERIAL" shell input keyevent KEYCODE_DPAD_RIGHT
sleep 2
adb -s "$SERIAL" exec-out screencap -p >"$OUT/home-right.png"
adb -s "$SERIAL" logcat -d -s TvHome:V >"$OUT/tvhome-log.txt"
if grep -q "served /api/home" "$OUT/tvhome-log.txt"; then echo "PASS the page asked for /api/home"; else echo "FAIL the page never asked for /api/home"; fi
if grep -q "console ERROR" "$OUT/tvhome-log.txt"; then echo "FAIL the page logged errors:"; grep "console ERROR" "$OUT/tvhome-log.txt"; else echo "PASS no page errors"; fi
# Takeover: switch the service on, leave TV Home, press Home, expect TV Home in front.
adb -s "$SERIAL" shell settings put secure enabled_accessibility_services com.rukoz.tvhome/com.rukoz.tvhome.HomeTakeover
adb -s "$SERIAL" shell settings put secure accessibility_enabled 1
sleep 5
adb -s "$SERIAL" shell am start -W -a android.settings.SETTINGS >/dev/null
sleep 3
adb -s "$SERIAL" shell input keyevent KEYCODE_HOME
sleep 4
adb -s "$SERIAL" exec-out screencap -p >"$OUT/after-home.png"
adb -s "$SERIAL" logcat -d -s TvHome:V >"$OUT/tvhome-log.txt"
top=$(adb -s "$SERIAL" shell dumpsys activity activities | grep -m1 -E "topResumedActivity|mResumedActivity")
if grep -q "takeover connected" "$OUT/tvhome-log.txt"; then echo "PASS takeover service connected"; else echo "FAIL takeover service never connected"; fi
if echo "$top" | grep -q "com.rukoz.tvhome/.HomeActivity"; then echo "PASS Home brought TV Home forward"; else echo "FAIL after Home the top activity is: $top"; fi
