# picture-auto-edit

Batch image auto-editor (Windows-friendly) for website images.

What it does (v1):
- Background blur
- Center-focused sharp subject area (simple center mask, no segmentation)
- Mild quality boost (contrast + unsharp mask)
- Logo overlay (bottom-right) on a subtle plate

## Quick start

1) Create a virtual environment (recommended)

```powershell
cd "C:\Users\orens\OneDrive\שולחן העבודה\alpha marketing projects\picture-auto-edit"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) Run on a single image

```powershell
python picture_auto_edit.py ^
  --input "C:\Users\orens\OneDrive\שולחן העבודה\alpha marketing projects\Midwest Flip\midwest flip website\images\40330379-1E1C-48C3-8971-1136EB901E58.jpg" ^
  --output ".\examples\out\example.jpg" ^
  --logo "C:\Users\orens\OneDrive\שולחן העבודה\alpha marketing projects\Midwest Flip\midwest flip website\images\logo.png" ^
  --plate-style frosted
```

## Batch mode (folder)

```powershell
python picture_auto_edit.py --input-dir "...\midwest flip website\images" --output-dir "...\midwest flip website\images_autoedited" --logo "...\logo.png" --dry-run
```

Notes for batch runs:
- Output folder should be **outside** the input folder (avoid re-processing outputs).
- Batch mode skips `logo.*` by default. You can add more with `--exclude`.

## Logo plate options

- `--plate-style frosted` (default): blurs the background under the logo and darkens it slightly
- `--plate-style dark`: solid darker plate
- `--plate-style light`: solid light plate

Extra knobs:
- `--plate-blur 10`
- `--plate-tint-alpha 110` (higher = darker)

## Notes
- By default, the script does **not** overwrite originals.
- You can control blur strength, center mask size, and logo size.
