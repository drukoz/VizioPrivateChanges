#!/bin/bash
# QA of TV Home on a headless emulator with a fake Plex on 127.0.0.1. Prints PASS/FAIL lines.
# Usage: bash android/scripts/emulator-qa.sh <apk> <output dir>
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/scripts/android-env.sh" || exit 1
APK="$1"; OUT="$2"; AVD=tvhome-qa; PORT=5630; S=emulator-$PORT; HOSTPLEX=32411; CDP=9363
mkdir -p "$OUT"
python3 -I "$ROOT/android/scripts/qa/fake_plex_serve.py" "$ROOT" $HOSTPLEX > "$OUT/plex.log" 2>&1 &
FP=$!
cleanup() { kill $FP 2>/dev/null; adb -s $S emu kill >/dev/null 2>&1; sleep 5; avdmanager delete avd -n $AVD >/dev/null 2>&1; }
trap cleanup EXIT
echo no | avdmanager create avd -n $AVD -k "system-images;android-36;google_apis;arm64-v8a" -d tv_1080p --force >/dev/null || exit 1
emulator -avd $AVD -port $PORT -no-window -no-audio -no-snapshot -no-boot-anim -gpu swiftshader_indirect > "$OUT/emulator.log" 2>&1 &
adb -s $S wait-for-device
booted=0
for i in $(seq 1 90); do
  if [ "$(adb -s $S shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; then booted=1; break; fi
  sleep 4
done
[ "$booted" = 1 ] || { echo "FAIL emulator did not boot"; exit 1; }
adb -s $S root >/dev/null; sleep 4; adb -s $S wait-for-device
adb -s $S shell iptables -I OUTPUT -d 192.168.0.0/16 -j REJECT
if adb -s $S shell iptables -S OUTPUT | grep -q "192.168.0.0/16.*REJECT"; then echo "PASS LAN blocked inside the emulator"; else echo "FAIL could not block the LAN; stopping before the app starts"; exit 1; fi
adb -s $S reverse tcp:32400 tcp:$HOSTPLEX
adb -s $S install -r "$APK" >/dev/null || { echo "FAIL install"; exit 1; }
adb -s $S logcat -c
adb -s $S shell am start -W -n com.rukoz.tvhome/.HomeActivity --es plexBaseUrl http://127.0.0.1:32400 >/dev/null
sleep 15
PID=$(adb -s $S shell pidof com.rukoz.tvhome | tr -d '\r')
adb -s $S forward tcp:$CDP localabstract:webview_devtools_remote_$PID >/dev/null
js() { node "$ROOT/android/scripts/qa/cdp_eval.mjs" $CDP "$1"; }
focused() { js 'document.querySelector(".focused").tileData.id'; }
key() { adb -s $S shell input keyevent "$1"; sleep 1; }
top() { adb -s $S shell dumpsys activity activities | grep -m1 -E "topResumedActivity|mResumedActivity"; }
log() { adb -s $S logcat -d -s TvHome:V; }

pass=0; fails=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1: $2"; fails=$((fails+1)); }

# 2.1 Home loaded
g=""
log | grep -q "served /api/home 200" || g="$g app log: $(log | grep -m1 'served /api/home' || echo 'no served /api/home line')"
grep -q "GET /hubs/continueWatching" "$OUT/plex.log" || g="$g plex.log: no GET /hubs/continueWatching"
if [ -z "$g" ]; then ok "home loaded"; else bad "home loaded" "${g# }"; fi

# 2.2 Rows
expected='["Continue Watching","Recently Added in Movies","Recently Added in TV Shows","Start Watching · TV Shows","Top Unwatched Movies","More in Fantasy · TV Shows","Top Movies in Family","Rediscover · TV Shows","Apps"]'
rows=$(js 'Array.prototype.map.call(document.querySelectorAll(".row-title"), function(e){return e.textContent})')
if [ "$rows" = "$expected" ]; then ok "9 rows titled as expected"; else bad "rows" "$rows"; fi

# 2.3 Posters
g=""
grep -q "GET /photo/:/transcode" "$OUT/plex.log" || g="$g plex.log: no GET /photo/:/transcode"
log | grep -q "served /img 200" || g="$g app log: $(log | grep -m1 'served /img' || echo 'no served /img line')"
if [ -z "$g" ]; then ok "posters served"; else bad "posters" "${g# }"; fi

# 2.4 No page errors
if log | grep -q "console ERROR"; then bad "no page errors" "$(log | grep -m1 'console ERROR')"; else ok "no page errors"; fi

# 2.5 Apps row
apps=$(js 'Array.prototype.map.call(document.querySelectorAll(".row")[8].querySelectorAll(".tile"), function(e){return e.tileData.id})')
if [ "$apps" = '["app:amazon-home"]' ]; then ok "apps row holds only app:amazon-home"; else bad "apps row" "$apps"; fi

# 2.6 Focus movement
g=""; f=$(focused)
[ "$f" = '"plex:4617"' ] || g="$g initial=$f"
key KEYCODE_DPAD_RIGHT; f=$(focused)
[ "$f" = '"plex:17346"' ] || g="$g right=$f"
key KEYCODE_DPAD_LEFT; f=$(focused)
[ "$f" = '"plex:4617"' ] || g="$g left=$f"
key KEYCODE_DPAD_DOWN; f=$(focused)
case "$f" in '"plex:'*) [ "$f" = '"plex:4617"' ] && g="$g down=$f" ;; *) g="$g down=$f" ;; esac
key KEYCODE_DPAD_UP; f=$(focused)
[ "$f" = '"plex:4617"' ] || g="$g up=$f"
if [ -z "$g" ]; then ok "focus moves right, left, down, up"; else bad "focus movement" "${g# }"; fi

# 2.7 Play with the deep link planned
key KEYCODE_DPAD_CENTER; sleep 3
g=""
log | grep -q "action PLAY_PLEX -> PLEX_DEEP_LINK" || g="$g no 'action PLAY_PLEX -> PLEX_DEEP_LINK' in the app log"
grep -q "GET /identity" "$OUT/plex.log" || g="$g plex.log: no GET /identity"
grep -q "GET /library/metadata/4617" "$OUT/plex.log" || g="$g plex.log: no GET /library/metadata/4617"
toast=$(js 'document.getElementById("toast").textContent')
[ "$toast" = '"Plex is not installed."' ] || g="$g toast=$toast"
if [ -z "$g" ]; then ok "play on plex:4617 plans PLEX_DEEP_LINK"; else bad "play deep link" "${g# }"; fi

# 2.8 Play fallback
key KEYCODE_DPAD_RIGHT
key KEYCODE_DPAD_CENTER; sleep 3
g=""
log | grep -q "action PLAY_PLEX -> LAUNCH_PACKAGE" || g="$g no 'action PLAY_PLEX -> LAUNCH_PACKAGE' in the app log"
toast=$(js 'document.getElementById("toast").textContent')
[ "$toast" = '"Plex is not installed."' ] || g="$g toast=$toast"
if [ -z "$g" ]; then ok "play on plex:17346 falls back to LAUNCH_PACKAGE"; else bad "play fallback" "${g# }"; fi

# 2.9 Bridge refusals
g=""
r=$(js 'JSON.parse(TvHome.action(JSON.stringify({kind:2,target:"hdmi2"})))')
case "$r" in *'"ok":false'*) ;; *) g="$g switch_input=$r" ;; esac
case "$r" in *'"message":"That works only on the VIZIO TV."'*) ;; *) g="$g switch_input_message=$r" ;; esac
r=$(js 'JSON.parse(TvHome.action(JSON.stringify({kind:1,target:"not a package!"})))')
case "$r" in *'"ok":false'*) ;; *) g="$g open_app_bad=$r" ;; esac
r=$(js 'JSON.parse(TvHome.action(JSON.stringify({kind:0,target:"abc"})))')
case "$r" in *'"ok":false'*) ;; *) g="$g play_bad=$r" ;; esac
r=$(js 'JSON.parse(TvHome.action("{"))')
case "$r" in *'"ok":false'*) ;; *) g="$g bad_json=$r" ;; esac
if [ -z "$g" ]; then ok "bridge refuses the 4 bad actions"; else bad "bridge refusals" "${g# }"; fi

# 2.10 Open an app
g=""
r=$(js 'JSON.parse(TvHome.action(JSON.stringify({kind:1,target:"com.android.settings"})))')
case "$r" in *'"ok":true'*) ;; *) g="$g action=$r" ;; esac
sleep 3
top | grep -q "com.android.settings" || g="$g top is: $(top)"
adb -s $S shell am start -W -n com.rukoz.tvhome/.HomeActivity --es plexBaseUrl http://127.0.0.1:32400 >/dev/null
sleep 3
top | grep -q "com.rukoz.tvhome/.HomeActivity" || g="$g top after restart is: $(top)"
if [ -z "$g" ]; then ok "open app com.android.settings and back"; else bad "open app" "${g# }"; fi

# 2.11 Takeover (block copied from android/scripts/emulator-smoke.sh)
adb -s $S shell settings put secure enabled_accessibility_services com.rukoz.tvhome/com.rukoz.tvhome.HomeTakeover
adb -s $S shell settings put secure accessibility_enabled 1
sleep 5
adb -s $S shell am start -W -a android.settings.SETTINGS >/dev/null
sleep 3
adb -s $S shell input keyevent KEYCODE_HOME
sleep 4
adb -s $S exec-out screencap -p > "$OUT/after-home.png"
t=$(top)
g=""
log | grep -q "takeover connected" || g="$g no 'takeover connected' in the app log"
echo "$t" | grep -q "com.rukoz.tvhome/.HomeActivity" || g="$g top after Home is: $t"
if [ -z "$g" ]; then ok "takeover brings TV Home forward on Home"; else bad "takeover" "${g# }"; fi

# 2.12 Amazon Home pause (last: the 15-minute pause cannot be cleared from outside)
reached=0; f=""
for i in $(seq 1 12); do
  key KEYCODE_DPAD_DOWN
  f=$(focused)
  if [ "$f" = '"app:amazon-home"' ]; then reached=1; break; fi
done
if [ "$reached" = 0 ]; then
  bad "amazon home pause" "focus never reached app:amazon-home (last: $f)"
else
  key KEYCODE_DPAD_CENTER
  sleep 4
  g=""
  log | grep -q "action AMAZON_HOME -> AMAZON_HOME" || g="$g no 'action AMAZON_HOME -> AMAZON_HOME' in the app log"
  t=$(top)
  echo "$t" | grep -q "com.rukoz.tvhome" && g="$g top is still TV Home: $t"
  key KEYCODE_HOME
  sleep 4
  t=$(top)
  echo "$t" | grep -q "com.rukoz.tvhome" && g="$g after Home the pause did not hold, top is: $t"
  if [ -z "$g" ]; then ok "amazon home pause keeps TV Home away"; else bad "amazon home pause" "${g# }"; fi
fi

# 2.13 Safety
g=""
grep -q "192.168." "$OUT/plex.log" && g="$g plex.log names a LAN address: $(grep -m1 '192.168.' "$OUT/plex.log")"
log | grep -q "served /api/home 5" && g="$g app log has: $(log | grep -m1 'served /api/home 5')"
if [ -z "$g" ]; then ok "no contact with the real Plex, no 5xx home responses"; else bad "safety" "${g# }"; fi

echo "RESULT $pass passed, $fails failed"
[ "$fails" = 0 ] || exit 1
