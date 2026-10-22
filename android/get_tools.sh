#!/bin/bash
# Downloads the Android build tools used by build.sh into ./tools (Linux x86-64; needs curl, unzip, a JDK 17+).
set -e
cd "$(dirname "$0")"; mkdir -p tools; cd tools
M=https://dl.google.com/android/maven2
curl -fL -o r8.jar     $M/com/android/tools/r8/8.5.35/r8-8.5.35.jar
curl -fL -o apksig.jar $M/com/android/tools/build/apksig/8.7.3/apksig-8.7.3.jar
curl -fL -o aapt2.jar  $M/com/android/tools/build/aapt2/8.7.3-12006047/aapt2-8.7.3-12006047-linux.jar
unzip -o -q aapt2.jar aapt2 && chmod +x aapt2
curl -fL -o platform.zip https://dl.google.com/android/repository/platform-35_r02.zip
unzip -o -q -j platform.zip android-35/android.jar && rm platform.zip
echo "tools ready"
