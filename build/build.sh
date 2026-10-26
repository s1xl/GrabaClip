#!/usr/bin/env bash
# Compila GrabaClip y arma el paquete portable para Windows.
# Funciona en Linux (por ejemplo en GitHub Actions con ubuntu-latest).
#
#   ./build/build.sh            -> dist/GrabaClip-vX.Y.Z-portable.zip
#
# Todo lo que se descarga esta fijado a versiones concretas para que la
# compilacion sea reproducible (requisito de SignPath).
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(tr -d ' \r\n' < "$RAIZ/VERSION")"
CACHE="$RAIZ/.cache"
OBJ="$RAIZ/build/obj"
DIST="$RAIZ/dist"
APP="$DIST/GrabaClip"
mkdir -p "$CACHE" "$OBJ"

LLVM_MINGW_URL="https://github.com/mstorsjo/llvm-mingw/releases/download/20240619/llvm-mingw-20240619-ucrt-ubuntu-20.04-x86_64.tar.xz"
PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20251014/cpython-3.12.12+20251014-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
FFMPEG_URL="${FFMPEG_URL:-https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip}"

descargar() {  # url destino
  if [ ! -s "$2" ]; then
    echo "==> Descargando $(basename "$2")"
    curl -fsSL --retry 3 -o "$2.tmp" "$1"
    mv "$2.tmp" "$2"
  fi
}

# ---------- compilador para Windows (llvm-mingw) ----------
if ! command -v x86_64-w64-mingw32-clang++ >/dev/null 2>&1; then
  if [ ! -d "$CACHE/llvm-mingw" ]; then
    descargar "$LLVM_MINGW_URL" "$CACHE/llvm-mingw.tar.xz"
    mkdir -p "$CACHE/llvm-mingw"
    tar xf "$CACHE/llvm-mingw.tar.xz" -C "$CACHE/llvm-mingw" --strip-components=1
  fi
  export PATH="$CACHE/llvm-mingw/bin:$PATH"
fi

IFS=. read -r V1 V2 V3 <<< "$VERSION"

recurso() {  # nombre_archivo descripcion icono(opcional) salida.o
  local rc="$OBJ/$1.rc"
  sed -e "s/GC_V1/$V1/g; s/GC_V2/$V2/g; s/GC_V3/$V3/g" \
      -e "s/GC_VSTR/\"$VERSION\"/g; s/GC_DESC/\"$2\"/g" \
      -e "s/GC_NAME/\"${1%.exe}\"/g; s/GC_FILE/\"$1\"/g" \
      "$RAIZ/native/version.rc.in" > "$rc"
  if [ -n "$3" ]; then
    cp "$3" "$OBJ/icono.ico"
    echo '1 ICON "icono.ico"' >> "$rc"
  fi
  (cd "$OBJ" && x86_64-w64-mingw32-windres "$(basename "$rc")" -O coff -o "$4")
}

echo "==> Compilando GrabaClip $VERSION"
recurso "GrabaClip.exe" "GrabaClip" "$RAIZ/native/lanzador/grabaclip.ico" "$OBJ/lanzador_res.o"
recurso "audiocap.exe" "GrabaClip - captura de audio" "" "$OBJ/audiocap_res.o"
x86_64-w64-mingw32-clang++ -std=c++17 -O2 -municode -mwindows -static -s \
  -o "$OBJ/GrabaClip.exe" "$RAIZ/native/lanzador/lanzador.cpp" "$OBJ/lanzador_res.o" -ladvapi32 -luser32
x86_64-w64-mingw32-clang++ -std=c++17 -O2 -municode -static -s \
  -o "$OBJ/audiocap.exe" "$RAIZ/native/audiocap/audiocap.cpp" "$OBJ/audiocap_res.o" -lole32 -luuid -lpropsys

# ---------- carpeta del programa ----------
rm -rf "$APP"
mkdir -p "$APP/runtime/ffmpeg"
cp "$OBJ/GrabaClip.exe" "$OBJ/audiocap.exe" "$APP/"
cp "$RAIZ"/src/*.py "$RAIZ/src/ui.html" "$RAIZ/src/grabaclip.ico" "$APP/"
cp "$RAIZ/docs/LEEME.txt" "$APP/LEEME.txt"
cp "$RAIZ/LICENSE" "$APP/LICENSE.txt"
cp "$RAIZ/docs/TERCEROS.txt" "$APP/TERCEROS.txt"
echo "$VERSION" > "$APP/VERSION"

# ---------- Python incluido ----------
descargar "$PYTHON_URL" "$CACHE/python.tar.gz"
tar xzf "$CACHE/python.tar.gz" -C "$APP/runtime"
rm -rf "$APP/runtime/python/include" "$APP/runtime/python/libs" \
       "$APP/runtime/python/Lib/idlelib" "$APP/runtime/python/Lib/test"
find "$APP/runtime/python" -name "__pycache__" -type d -prune -exec rm -rf {} +

# dependencias de la interfaz ya instaladas (asi no hace falta internet al abrir).
# Se instalan sin resolver dependencias (--no-deps) porque la lista ya es completa.
SITE="$APP/runtime/python/Lib/site-packages"
if pip install --quiet --disable-pip-version-check --no-compile --no-deps --target "$SITE" \
     --platform win_amd64 --python-version 3.12 --implementation cp --only-binary=:all: \
     -r "$RAIZ/requirements-binarios.txt" && \
   pip install --quiet --disable-pip-version-check --no-compile --no-deps --target "$SITE" \
     -r "$RAIZ/requirements-puros.txt"; then
  echo "==> Dependencias incluidas"
else
  echo "AVISO: no se pudieron incluir pywebview/keyboard; se instalaran en el primer arranque" >&2
fi
find "$SITE" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true

# ---------- FFmpeg incluido ----------
descargar "$FFMPEG_URL" "$CACHE/ffmpeg.zip"
rm -rf "$OBJ/ff" && mkdir -p "$OBJ/ff"
unzip -q "$CACHE/ffmpeg.zip" -d "$OBJ/ff"
FF="$(find "$OBJ/ff" -maxdepth 1 -mindepth 1 -type d | head -1)"
cp "$FF/bin/ffmpeg.exe" "$FF/bin/ffprobe.exe" "$FF"/bin/*.dll "$APP/runtime/ffmpeg/"
cp "$FF/LICENSE.txt" "$APP/runtime/ffmpeg/LICENSE.txt"
rm -rf "$OBJ/ff"

# ---------- zip ----------
ZIP="$DIST/GrabaClip-v$VERSION-portable.zip"
rm -f "$ZIP"
(cd "$DIST" && zip -qr -9 "$(basename "$ZIP")" GrabaClip)
echo "==> Listo: $ZIP ($(du -h "$ZIP" | cut -f1))"

# ---------- instalador (opcional: solo si hay NSIS) ----------
if command -v makensis >/dev/null 2>&1; then
  SETUP="$DIST/GrabaClip-v$VERSION-instalador.exe"
  if ! makensis -V2 -DVERSION="$VERSION" -DORIGEN="$APP" -DSALIDA="$SETUP" "$RAIZ/build/instalador.nsi" > "$OBJ/nsis.log" 2>&1; then
    # en GitHub Actions, las ultimas lineas quedan como anotaciones visibles en la ejecucion
    tail -15 "$OBJ/nsis.log" | while IFS= read -r l; do echo "::error title=NSIS::$l"; done
    exit 1
  fi
  echo "==> Listo: $SETUP ($(du -h "$SETUP" | cut -f1))"
else
  echo "==> (sin NSIS: no se arma el instalador)"
fi
