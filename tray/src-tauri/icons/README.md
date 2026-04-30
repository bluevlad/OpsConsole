# OpsConsole Tray Icons

Tauri 빌드에는 다음 아이콘이 필요합니다:

- `icon.icns` (macOS, 1024x1024 base)
- `icon.ico` (Windows, multi-resolution: 16/32/48/64/128/256)
- `32x32.png` / `128x128.png` / `128x128@2x.png` (Linux)

## 자동 생성

원본 1024x1024 PNG 1장만 준비하면 Tauri CLI 가 다 생성해줍니다:

```bash
cd tray
npx @tauri-apps/cli icon path/to/source-1024.png -o src-tauri/icons
```

## 임시 placeholder

ImageMagick 또는 Pillow 로 단색 PNG 생성:

```bash
python3 -c "
from PIL import Image
img = Image.new('RGBA', (1024, 1024), (91, 139, 255, 255))
img.save('icon.png')
"
npx @tauri-apps/cli icon icon.png -o src-tauri/icons
```
