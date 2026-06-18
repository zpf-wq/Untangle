#!/bin/bash
# 构建 Untangle.app(原生 Mac 前端)。
# 用法:cd macapp && ./build_app.sh
# 产物:macapp/Untangle.app  —— 双击即可运行。
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="Untangle"
BUNDLE="${APP_NAME}.app"
ICON_SRC="AppIcon.png"   # 1024+ 的方形 PNG 源图

echo "==> 编译(release)…"
swift build -c release

BIN_PATH="$(swift build -c release --show-bin-path)/${APP_NAME}"
if [[ ! -f "$BIN_PATH" ]]; then
  echo "构建失败:找不到可执行文件 $BIN_PATH" >&2
  exit 1
fi

echo "==> 组装 ${BUNDLE} …"
rm -rf "$BUNDLE"
mkdir -p "${BUNDLE}/Contents/MacOS"
mkdir -p "${BUNDLE}/Contents/Resources"
cp "$BIN_PATH" "${BUNDLE}/Contents/MacOS/${APP_NAME}"

# ---- 生成应用图标 AppIcon.icns ----
ICON_LINE=""
if [[ -f "$ICON_SRC" ]]; then
  echo "==> 生成图标(从 ${ICON_SRC})…"
  ICONSET="$(mktemp -d)/AppIcon.iconset"
  mkdir -p "$ICONSET"
  for spec in "16:16x16" "32:16x16@2x" "32:32x32" "64:32x32@2x" \
              "128:128x128" "256:128x128@2x" "256:256x256" "512:256x256@2x" \
              "512:512x512" "1024:512x512@2x"; do
    size="${spec%%:*}"; name="${spec##*:}"
    sips -z "$size" "$size" "$ICON_SRC" --out "${ICONSET}/icon_${name}.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "${BUNDLE}/Contents/Resources/AppIcon.icns"
  ICON_LINE="    <key>CFBundleIconFile</key><string>AppIcon</string>"
else
  echo "（未找到 ${ICON_SRC},跳过图标生成,使用默认图标)"
fi

cat > "${BUNDLE}/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key><string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key><string>com.untangle.app</string>
    <key>CFBundleVersion</key><string>1.0</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleExecutable</key><string>${APP_NAME}</string>
${ICON_LINE}
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSPrincipalClass</key><string>NSApplication</string>
</dict>
</plist>
PLIST

# Ad-hoc 签名,避免 Gatekeeper 直接拦截(本地自用足够)
echo "==> Ad-hoc 签名…"
codesign --force --deep --sign - "$BUNDLE" >/dev/null 2>&1 || true

echo ""
echo "✅ 完成:$(pwd)/${BUNDLE}"
echo "   双击运行,或执行:open \"${BUNDLE}\""
