from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter


SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class Settings:
    blur_radius: float = 18.0
    center_scale: float = 0.72  # fraction of width/height used for the sharp center area
    center_roundness: int = 28  # px corner radius for the center mask
    feather: int = 18  # px
    contrast: float = 1.06
    sharpness: float = 1.10
    unsharp_radius: float = 1.4
    unsharp_percent: int = 140
    unsharp_threshold: int = 2
    logo_scale: float = 0.13  # fraction of image width
    logo_opacity: float = 0.88
    logo_padding: int = 24
    plate_padding: int = 14
    plate_alpha: int = 215
    plate_style: str = "frosted"  # light | dark | frosted
    plate_blur_radius: float = 10.0
    plate_tint_alpha: int = 110  # 0-255, higher = darker
    plate_border_alpha: int = 210


def _open_image(path: Path) -> Image.Image:
    img = Image.open(path)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    return img


def _rounded_rect_mask(size: tuple[int, int], radius: int) -> Image.Image:
    w, h = size
    if radius <= 0:
        return Image.new("L", (w, h), 255)

    # Pillow has ImageDraw.rounded_rectangle but to avoid extra import,
    # build via rectangles + blur feather later.
    # Base rectangle
    rect = Image.new("L", (w, h), 255)

    # Cut corners using circles
    corner = Image.new("L", (radius * 2, radius * 2), 0)
    corner = corner.filter(ImageFilter.GaussianBlur(0))

    # Create crisp rounded corners using ellipses
    from PIL import ImageDraw  # local import

    cd = ImageDraw.Draw(corner)
    cd.ellipse((0, 0, radius * 2 - 1, radius * 2 - 1), fill=255)

    rect_draw = ImageDraw.Draw(rect)
    rect_draw.rectangle((0, 0, w - 1, h - 1), fill=255)

    # Clear corners
    clear = Image.new("L", (radius * 2, radius * 2), 0)
    rect.paste(clear, (0, 0))
    rect.paste(clear, (w - radius * 2, 0))
    rect.paste(clear, (0, h - radius * 2))
    rect.paste(clear, (w - radius * 2, h - radius * 2))

    # Paste rounded corners
    rect.paste(corner.crop((0, 0, radius, radius)), (0, 0))
    rect.paste(corner.crop((radius, 0, radius * 2, radius)), (w - radius, 0))
    rect.paste(corner.crop((0, radius, radius, radius * 2)), (0, h - radius))
    rect.paste(corner.crop((radius, radius, radius * 2, radius * 2)), (w - radius, h - radius))

    mask = rect
    return mask


def _feather_mask(mask: Image.Image, feather: int) -> Image.Image:
    if feather <= 0:
        return mask
    return mask.filter(ImageFilter.GaussianBlur(feather))


def _quality_boost(img_rgb: Image.Image, s: Settings) -> Image.Image:
    img = ImageEnhance.Contrast(img_rgb).enhance(s.contrast)
    img = ImageEnhance.Sharpness(img).enhance(s.sharpness)
    img = img.filter(
        ImageFilter.UnsharpMask(radius=s.unsharp_radius, percent=s.unsharp_percent, threshold=s.unsharp_threshold)
    )
    return img


def _overlay_logo(base_rgba: Image.Image, logo_path: Path, s: Settings) -> Image.Image:
    if not logo_path.exists():
        return base_rgba

    logo = Image.open(logo_path).convert("RGBA")

    bw, bh = base_rgba.size
    target_w = max(48, int(bw * s.logo_scale))
    logo.thumbnail((target_w, target_w), Image.Resampling.LANCZOS)

    # Apply opacity
    if s.logo_opacity < 1.0:
        alpha = logo.getchannel("A")
        alpha = alpha.point(lambda a: int(a * s.logo_opacity))
        logo.putalpha(alpha)

    plate_w = logo.size[0] + s.plate_padding * 2
    plate_h = logo.size[1] + s.plate_padding * 2

    x = bw - plate_w - s.logo_padding
    y = bh - plate_h - s.logo_padding

    from PIL import ImageDraw  # local import

    radius = 18

    def _rounded_mask(w: int, h: int, r: int) -> Image.Image:
        m = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(m)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
        return m

    if s.plate_style == "dark":
        plate = Image.new("RGBA", (plate_w, plate_h), (0, 0, 0, s.plate_alpha))
    elif s.plate_style == "light":
        plate = Image.new("RGBA", (plate_w, plate_h), (255, 255, 255, s.plate_alpha))
    else:
        # Frosted: blur what is behind the plate and darken it slightly.
        region = base_rgba.crop((x, y, x + plate_w, y + plate_h))
        region = region.filter(ImageFilter.GaussianBlur(s.plate_blur_radius))
        tint = Image.new("RGBA", (plate_w, plate_h), (0, 0, 0, s.plate_tint_alpha))
        plate = Image.alpha_composite(region, tint)
        mask = _rounded_mask(plate_w, plate_h, radius)
        clipped = Image.new("RGBA", (plate_w, plate_h), (0, 0, 0, 0))
        clipped.paste(plate, (0, 0), mask)
        plate = clipped

    plate_draw = ImageDraw.Draw(plate)
    plate_draw.rounded_rectangle(
        (0, 0, plate_w - 1, plate_h - 1),
        radius=radius,
        outline=(255, 255, 255, s.plate_border_alpha),
        width=2,
    )
    plate.alpha_composite(logo, (s.plate_padding, s.plate_padding))

    out = base_rgba.copy()
    out.alpha_composite(plate, (x, y))
    return out


def process_one(*, input_path: Path, output_path: Path, logo_path: Path | None, s: Settings) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    original = _open_image(input_path)
    base = original.convert("RGB")

    # Background blur
    bg = base.filter(ImageFilter.GaussianBlur(s.blur_radius))

    # Center-focused sharp area
    w, h = base.size
    fw, fh = int(w * s.center_scale), int(h * s.center_scale)
    left = (w - fw) // 2
    top = (h - fh) // 2

    fg = base.crop((left, top, left + fw, top + fh))
    fg = _quality_boost(fg, s)

    # Build rounded + feathered mask
    mask = _rounded_rect_mask((fw, fh), radius=min(s.center_roundness, fw // 4, fh // 4))
    mask = _feather_mask(mask, s.feather)

    composed = bg.copy()
    composed.paste(fg, (left, top), mask)

    out = composed.convert("RGBA")
    if logo_path:
        out = _overlay_logo(out, logo_path, s)

    # Save
    ext = output_path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        out.convert("RGB").save(output_path, quality=88, optimize=True, progressive=True)
    elif ext == ".png":
        out.save(output_path, optimize=True)
    else:
        # webp (default)
        out.save(output_path, "WEBP", quality=86, method=6)


def iter_images(input_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for p in input_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            paths.append(p)
    return sorted(paths)


def _is_excluded(path: Path, *, input_dir: Path, exclude_globs: list[str]) -> bool:
    try:
        rel = path.relative_to(input_dir)
    except Exception:
        rel = path
    rel_posix = rel.as_posix()
    name = path.name

    for pat in exclude_globs:
        # Match both against rel path and filename for convenience
        if Path(rel_posix).match(pat) or Path(name).match(pat):
            return True
    return False


def _print_dry_run_summary(pairs: list[tuple[Path, Path]], *, limit: int = 30) -> None:
    total = len(pairs)
    print(f"DRY-RUN: {total} images")
    if total == 0:
        return
    head = pairs[: min(limit, total)]
    for src, dst in head:
        print(f"- {src} -> {dst}")
    if total > limit:
        print(f"... ({total - limit} more not shown)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-edit images (blur background + center focus + logo overlay)")
    ap.add_argument("--input", type=Path, help="Single input image path")
    ap.add_argument("--output", type=Path, help="Single output image path")
    ap.add_argument("--input-dir", type=Path, help="Folder to process recursively")
    ap.add_argument("--output-dir", type=Path, help="Output folder (mirrors structure)")
    ap.add_argument("--logo", type=Path, required=False, help="Logo path (PNG recommended)")
    ap.add_argument("--dry-run", action="store_true", help="List planned operations without writing")
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Glob pattern to exclude (can be repeated). Example: --exclude '**/logo.*'",
    )
    ap.add_argument("--dry-run-limit", type=int, default=30, help="How many dry-run items to print")

    ap.add_argument("--blur", type=float, default=Settings.blur_radius)
    ap.add_argument("--center-scale", type=float, default=Settings.center_scale)
    ap.add_argument("--feather", type=int, default=Settings.feather)
    ap.add_argument("--logo-scale", type=float, default=Settings.logo_scale)
    ap.add_argument(
        "--plate-style",
        choices=["light", "dark", "frosted"],
        default=Settings.plate_style,
        help="Logo background plate style",
    )
    ap.add_argument("--plate-blur", type=float, default=Settings.plate_blur_radius, help="Blur radius for frosted plate")
    ap.add_argument(
        "--plate-tint-alpha",
        type=int,
        default=Settings.plate_tint_alpha,
        help="0-255. Higher = darker frosted plate",
    )

    args = ap.parse_args()

    s = Settings(
        blur_radius=args.blur,
        center_scale=args.center_scale,
        feather=args.feather,
        logo_scale=args.logo_scale,
        plate_style=args.plate_style,
        plate_blur_radius=args.plate_blur,
        plate_tint_alpha=args.plate_tint_alpha,
    )

    logo_path = args.logo if args.logo else None
    exclude_globs: list[str] = list(args.exclude)

    # Single
    if args.input and args.output:
        if args.dry_run:
            print(f"DRY-RUN: {args.input} -> {args.output}")
            return 0
        process_one(input_path=args.input, output_path=args.output, logo_path=logo_path, s=s)
        print(f"Wrote: {args.output}")
        return 0

    # Batch
    if args.input_dir and args.output_dir:
        # Safe defaults for batch runs
        if not exclude_globs:
            exclude_globs = ["logo.*", "**/logo.*"]

        images = [
            p
            for p in iter_images(args.input_dir)
            if not _is_excluded(p, input_dir=args.input_dir, exclude_globs=exclude_globs)
        ]
        if not images:
            print(f"No images found in: {args.input_dir}")
            return 2

        pairs: list[tuple[Path, Path]] = []
        for src in images:
            rel = src.relative_to(args.input_dir)
            dst = args.output_dir / rel
            pairs.append((src, dst))

        if args.dry_run:
            _print_dry_run_summary(pairs, limit=max(1, int(args.dry_run_limit)))
            return 0

        for src, dst in pairs:
            process_one(input_path=src, output_path=dst, logo_path=logo_path, s=s)

        print(f"Done. Processed {len(images)} images -> {args.output_dir}")
        return 0

    ap.error("Provide either --input/--output OR --input-dir/--output-dir")


if __name__ == "__main__":
    raise SystemExit(main())
