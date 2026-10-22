#!/bin/bash
# Builds out/SatPeak.apk without Gradle: aapt2 + javac + d8 + apksig.
# Run ./get_tools.sh once first.  Signing key: $SATPEAK_KEYSTORE (PKCS12, alias "satpeak"),
# password in $SATPEAK_KEYPASS. If no keystore exists a new one is generated (keep it safe -
# app updates must be signed with the same key).
set -e
cd "$(dirname "$0")"
T=tools; AJ=$T/android.jar
KS=${SATPEAK_KEYSTORE:-satpeak-release.p12}; PW=${SATPEAK_KEYPASS:-satpeak-qo100}
VC=${VERSION_CODE:-1}; VN=${VERSION_NAME:-1.0}
rm -rf out && mkdir -p out/flat out/classes out/dex assets
cp ../server/index.html assets/index.html
$T/aapt2 compile --dir res -o out/flat/
$T/aapt2 link -o out/base.apk -I $AJ --manifest AndroidManifest.xml -A assets out/flat/*.flat \
  --min-sdk-version 24 --target-sdk-version 34 --version-code $VC --version-name $VN --auto-add-overlay
javac -source 8 -target 8 -nowarn -Xlint:-options -bootclasspath $AJ -classpath $AJ -d out/classes $(find src -name '*.java')
java -cp $T/r8.jar com.android.tools.r8.D8 --release --min-api 24 --lib $AJ --output out/dex $(find out/classes -name '*.class')
cp out/base.apk out/unsigned.apk
(cd out/dex && zip -q -0 ../unsigned.apk classes.dex)
if [ ! -f "$KS" ]; then
  echo "No keystore found - generating $KS"
  keytool -genkeypair -storetype PKCS12 -keystore "$KS" -storepass "$PW" -keypass "$PW" -alias satpeak \
    -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=SatPeak, OU=QO-100, O=SatPeak, C=GB"
fi
javac -nowarn -cp $T/apksig.jar -d out SignApk.java
java -cp $T/apksig.jar:out SignApk out/unsigned.apk out/SatPeak.apk "$KS" "$PW" satpeak
ls -la out/SatPeak.apk
