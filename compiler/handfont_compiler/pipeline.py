from __future__ import annotations

import json
import hashlib
import math
import re
import shutil
import statistics
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image
from ufo2ft import compileTTF
from ufoLib2 import Font


_X_HEIGHT_GLYPHS = frozenset("acemnorsuvwxz")
_X_HEIGHT_REFERENCES = frozenset("one")


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "", value)
    return cleaned or "Untitled"


def _trace_cache_key(image_path: Path, processing: dict[str, Any], placement: tuple[float, float] | None, cap_height: int) -> str:
    stat = image_path.stat()
    payload = {
        "version": 1,
        "path": str(image_path.resolve()),
        "size": stat.st_size,
        "modified": stat.st_mtime_ns,
        "processing": processing,
        "placement": placement,
        "capHeight": cap_height,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def preprocess_image(source: Path, settings: dict[str, Any]) -> np.ndarray:
    color = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if color is None:
        raise ValueError(f"Could not decode image: {source}")
    image = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    if settings.get("invert", False):
        image = cv2.bitwise_not(image)
        color = cv2.bitwise_not(color)
    threshold = int(settings.get("threshold", 160))
    _, mask = cv2.threshold(image, threshold, 255, cv2.THRESH_BINARY_INV)
    if not settings.get("invert", False):
        channel_spread = color.max(axis=2).astype(np.int16) - color.min(axis=2).astype(np.int16)
        neutral_ink = np.where(channel_spread <= 30, 255, 0).astype(np.uint8)
        mask = cv2.bitwise_and(mask, neutral_ink)
    despeckle = max(0, int(settings.get("despeckle", 0)))
    if despeckle:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        filtered = np.zeros_like(mask)
        for index in range(1, count):
            if stats[index, cv2.CC_STAT_AREA] >= despeckle:
                filtered[labels == index] = 255
        mask = filtered
    smoothing = max(0, int(settings.get("smoothing", 0)))
    if smoothing:
        kernel = smoothing * 2 + 1
        mask = cv2.GaussianBlur(mask, (kernel, kernel), 0)
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    return mask


def mask_contours(mask: np.ndarray, cap_height: int, placement: tuple[float, float] | None = None, trace_preset: str = "balanced") -> tuple[list[list[tuple[int, int]]], tuple[int, int, int, int]]:
    points = cv2.findNonZero(mask)
    if points is None:
        return [], (0, 0, 0, 0)
    x, y, width, height = cv2.boundingRect(points)
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if placement:
        baseline_y, cap_height_y = placement
        scale = cap_height / max(baseline_y - cap_height_y, 1)
    else:
        baseline_y = float(y + height)
        scale = cap_height / max(height, 1)
    converted: list[list[tuple[int, int]]] = []
    hierarchy_rows = hierarchy[0] if hierarchy is not None else []
    for index, contour in enumerate(contours):
        minimum_area = 0.5 if trace_preset == "preserve" else 2
        if cv2.contourArea(contour) < minimum_area:
            continue
        epsilon_factor = {"preserve": 0.00015, "balanced": 0.0015, "smooth": 0.004}.get(trace_preset, 0.0015)
        epsilon = max(0.15 if trace_preset == "preserve" else 0.6, epsilon_factor * cv2.arcLength(contour, True))
        contour = cv2.approxPolyDP(contour, epsilon, True)
        path = [(round((int(px) - x) * scale), round((baseline_y - int(py)) * scale)) for [[px, py]] in contour]
        is_hole = bool(len(hierarchy_rows) and hierarchy_rows[index][3] >= 0)
        signed_area = sum(path[i][0] * path[(i + 1) % len(path)][1] - path[(i + 1) % len(path)][0] * path[i][1] for i in range(len(path)))
        if (is_hole and signed_area > 0) or (not is_hole and signed_area < 0):
            path.reverse()
        if len(path) >= 3:
            converted.append(path)
    return converted, (x, y, width, height)


def _draw_paths(glyph: Any, paths: list[list[tuple[int, int]]], x_offset: int) -> None:
    pen = glyph.getPen()
    for path in paths:
        pen.moveTo((path[0][0] + x_offset, path[0][1]))
        for point in path[1:]:
            pen.lineTo((point[0] + x_offset, point[1]))
        pen.closePath()


def _outline_height(paths: list[list[tuple[int, int]]]) -> int:
    ys = [point[1] for path in paths for point in path]
    return max(ys) - min(ys) if ys else 0


def _normalize_x_height(paths: list[list[tuple[int, int]]], target_height: float) -> list[list[tuple[int, int]]]:
    """Scale body height around the baseline without widening strokes or glyphs."""
    current_height = _outline_height(paths)
    if current_height <= 0 or target_height <= 0:
        return paths
    scale = target_height / current_height
    return [[(x, round(y * scale)) for x, y in path] for path in paths]


def _apply_glyph_transform(paths: list[list[tuple[int, int]]], transform: dict[str, Any]) -> list[list[tuple[int, int]]]:
    if not paths:
        return paths
    scale_x = float(transform.get("scaleX", 1))
    scale_y = float(transform.get("scaleY", 1))
    translate_x = float(transform.get("translateX", 0))
    translate_y = float(transform.get("translateY", 0))
    angle = math.radians(float(transform.get("rotation", 0)))
    cosine, sine = math.cos(angle), math.sin(angle)
    xs = [point[0] for path in paths for point in path]
    center_x = (min(xs) + max(xs)) / 2
    transformed: list[list[tuple[int, int]]] = []
    for path in paths:
        next_path: list[tuple[int, int]] = []
        for x, y in path:
            local_x, local_y = (x - center_x) * scale_x, y * scale_y
            rotated_x = local_x * cosine - local_y * sine
            rotated_y = local_x * sine + local_y * cosine
            next_path.append((round(rotated_x + center_x + translate_x), round(rotated_y + translate_y)))
        transformed.append(next_path)
    return transformed


def _add_required_glyphs(font: Font, space_width: int) -> None:
    notdef = font.newGlyph(".notdef")
    notdef.width = 600
    pen = notdef.getPen()
    pen.moveTo((60, 0)); pen.lineTo((540, 0)); pen.lineTo((540, 700)); pen.lineTo((60, 700)); pen.closePath()
    pen.moveTo((140, 80)); pen.lineTo((140, 620)); pen.lineTo((460, 620)); pen.lineTo((460, 80)); pen.closePath()
    space = font.newGlyph("space")
    space.width = space_width
    space.unicode = 0x20


def _automatic_contextual_alternates(glyphs: list[dict[str, Any]]) -> str:
    """Generate stable contextual variation for imported alternate drawings."""
    compiled_names = [str(item["glyphName"]) for item in glyphs]
    groups: dict[str, list[tuple[int, str]]] = {}
    for item in glyphs:
        variant_index = int(item.get("variantIndex", 0))
        group = item.get("variantGroup")
        if variant_index > 0 and group:
            groups.setdefault(str(group), []).append((variant_index, str(item["glyphName"])))

    lines: list[str] = []
    stylistic_substitutions: dict[int, list[tuple[str, str]]] = {}
    for group_number, (base, alternates) in enumerate(sorted(groups.items())):
        if base not in compiled_names:
            continue
        choices = [base, *[name for _, name in sorted(alternates)]]
        for variant_index, alternate_name in alternates:
            stylistic_substitutions.setdefault(variant_index, []).append((base, alternate_name))
        # Repeated characters must cycle explicitly. Hash-only context can leave
        # some glyphs permanently in their base-form bucket (for example uuuu).
        for choice_index, predecessor in enumerate(choices):
            replacement = choices[(choice_index + 1) % len(choices)]
            if replacement != base:
                lines.append(f"sub {predecessor} {base}' by {replacement};")
        buckets: list[list[str]] = [[] for _ in choices]
        for name in compiled_names:
            if name in choices:
                continue
            bucket = sum((index + 1) * ord(char) for index, char in enumerate(name)) % len(choices)
            buckets[bucket].append(name)
        for choice_index, replacement in enumerate(choices[1:], start=1):
            if not buckets[choice_index]:
                continue
            class_name = f"@HFContext{group_number}_{choice_index}"
            lines.append(f"{class_name} = [{' '.join(buckets[choice_index])}];")
            lines.append(f"sub {class_name} {base}' by {replacement};")

    if not lines:
        return ""
    blocks = ["feature calt {\n  " + "\n  ".join(lines) + "\n} calt;"]
    for variant_index, substitutions in sorted(stylistic_substitutions.items()):
        if not 1 <= variant_index <= 20:
            continue
        tag = f"ss{variant_index:02d}"
        rules = "\n  ".join(f"sub {base} by {alternate};" for base, alternate in sorted(substitutions))
        blocks.append(f"feature {tag} {{\n  {rules}\n}} {tag};")
    return "\n\n".join(blocks)


def _expanded_kerning_pairs(style: dict[str, Any]) -> dict[tuple[str, str], int]:
    """Apply a character's kerning exception to all of its imported forms."""
    available = [source for source in style.get("glyphs", []) if source.get("status") != "missing" and source.get("sourceImagePath")]

    def forms(base_name: str) -> list[str]:
        matches = []
        for source in available:
            glyph_name = str(source.get("glyphName", ""))
            if glyph_name == base_name or str(source.get("variantGroup", "")) == base_name:
                matches.append(glyph_name)
        return matches or [base_name]

    expanded: dict[tuple[str, str], int] = {}
    pairs = style.get("kerningPairs", [])
    for pair in (item for item in pairs if item.get("scope", "all-forms") != "exact-forms"):
        left, right = pair.get("leftGlyph"), pair.get("rightGlyph")
        if not left or not right:
            continue
        for left_form in forms(str(left)):
            for right_form in forms(str(right)):
                expanded[(left_form, right_form)] = int(pair.get("value", 0))
    # Exact-form rules are applied last so they override character-level rules.
    for pair in (item for item in pairs if item.get("scope") == "exact-forms"):
        left, right = pair.get("leftGlyph"), pair.get("rightGlyph")
        if left and right:
            expanded[(str(left), str(right))] = int(pair.get("value", 0))
    return expanded


def compile_project(project_path: str, style_id: str, output_directory: str | None = None) -> dict[str, Any]:
    root = Path(project_path).expanduser().resolve()
    project_file = root / "project.json"
    if not project_file.is_file():
        raise ValueError("project.json was not found")
    project = json.loads(project_file.read_text(encoding="utf-8"))
    style = next((item for item in project.get("styles", []) if item.get("id") == style_id), None)
    if style is None:
        raise ValueError(f"Style not found: {style_id}")

    family = str(project.get("familyName", "Untitled Hand"))
    style_name = str(style.get("name", "Regular"))
    basename = f"{_safe_name(family)}-{_safe_name(style_name)}"
    output = Path(output_directory).resolve() if output_directory else root / "generated" / style_id
    output.mkdir(parents=True, exist_ok=True)
    vectors = root / "vectors" / style_id
    vectors.mkdir(parents=True, exist_ok=True)
    trace_cache_dir = vectors / ".trace-cache"
    trace_cache_dir.mkdir(parents=True, exist_ok=True)

    font = Font()
    font.info.familyName = family
    font.info.styleName = style_name
    font.info.unitsPerEm = int(project.get("unitsPerEm", 1000))
    font.info.ascender = int(project.get("ascender", 800))
    font.info.descender = int(project.get("descender", -200))
    font.info.capHeight = int(project.get("capHeight", 700))
    font.info.xHeight = int(project.get("xHeight", 500))
    font.info.postscriptFontName = basename
    _add_required_glyphs(font, int(style.get("defaultSpaceWidth", 250)))
    for pair, value in _expanded_kerning_pairs(style).items():
        font.kerning[pair] = value
    warnings: list[str] = []
    compiled_count = 0
    compiled_sources: list[dict[str, Any]] = []
    glyph_bounds: dict[str, dict[str, int]] = {}

    runtime_trace_cache: dict[str, tuple[list[list[tuple[int, int]]], tuple[int, int, int, int]]] = {}

    def extract_paths(source: dict[str, Any]) -> tuple[list[list[tuple[int, int]]], tuple[int, int, int, int]]:
        image_path = Path(str(source["sourceImagePath"]))
        if not image_path.is_absolute():
            image_path = root / image_path
        placement: tuple[float, float] | None = None
        template_placement = source.get("templatePlacement")
        if isinstance(template_placement, dict):
            template = next((item for item in project.get("templates", []) if item.get("id") == template_placement.get("templateId") and item.get("pageNumber") == template_placement.get("pageNumber")), None)
            if template:
                cell = next((item for item in template.get("cells", []) if item.get("glyphName") == source.get("glyphName")), None)
                if cell:
                    drawing_y = float(cell["drawingBounds"]["y"])
                    placement = (float(cell["guides"]["baselineY"]) - drawing_y, float(cell["guides"]["capHeightY"]) - drawing_y)
        processing = source.get("processing", {})
        cap_height = int(project.get("capHeight", 700))
        cache_key = _trace_cache_key(image_path, processing, placement, cap_height)
        if cache_key in runtime_trace_cache:
            return runtime_trace_cache[cache_key]
        safe_glyph_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(source.get("glyphName", "glyph")))
        cache_path = trace_cache_dir / f"{safe_glyph_name}-{cache_key[:20]}.json"
        if cache_path.is_file():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                result = ([[tuple(point) for point in path] for path in cached["paths"]], tuple(cached["bounds"]))
                runtime_trace_cache[cache_key] = result
                return result
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                pass
        mask = preprocess_image(image_path, processing)
        result = mask_contours(mask, cap_height, placement, str(processing.get("tracePreset", "balanced")))
        temporary_cache = cache_path.with_suffix(".json.tmp")
        temporary_cache.write_text(json.dumps({"paths": result[0], "bounds": result[1]}, separators=(",", ":")), encoding="utf-8")
        temporary_cache.replace(cache_path)
        runtime_trace_cache[cache_key] = result
        return result

    reference_heights: list[int] = []
    for source in style.get("glyphs", []):
        character = str(source.get("character", ""))
        image_value = source.get("sourceImagePath")
        if character not in _X_HEIGHT_REFERENCES or not image_value or source.get("status") == "missing":
            continue
        image_path = Path(str(image_value))
        if not image_path.is_absolute():
            image_path = root / image_path
        if not image_path.is_file():
            continue
        reference_paths, _ = extract_paths(source)
        height = _outline_height(reference_paths)
        if height > 0:
            reference_heights.append(height)
    target_x_height = statistics.median(reference_heights) if reference_heights else float(project.get("xHeight", 500))

    for source in style.get("glyphs", []):
        image_value = source.get("sourceImagePath")
        if not image_value or source.get("status") == "missing":
            continue
        image_path = Path(image_value)
        if not image_path.is_absolute():
            image_path = root / image_path
        if not image_path.is_file():
            warnings.append(f"{source.get('glyphName', '?')}: source image was not found")
            continue
        paths, bounds = extract_paths(source)
        if not paths:
            warnings.append(f"{source.get('glyphName', '?')}: no outline was extracted")
            continue
        if str(source.get("character", "")) in _X_HEIGHT_GLYPHS:
            paths = _normalize_x_height(paths, target_x_height)
        paths = _apply_glyph_transform(paths, source.get("transform", {}))
        glyph_name = str(source.get("glyphName") or f"uni{int(source['unicode']):04X}")
        glyph = font.newGlyph(glyph_name)
        metrics = source.get("metrics", {})
        left = int(metrics.get("leftSideBearing", style.get("defaultLeftBearing", 40)))
        glyph.width = int(metrics.get("advanceWidth", 600))
        if source.get("unicode") is not None:
            glyph.unicode = int(source["unicode"])
        _draw_paths(glyph, paths, left)
        all_x = [point[0] + left for path in paths for point in path]
        all_y = [point[1] for path in paths for point in path]
        glyph_bounds[glyph_name] = {
            "xMin": min(all_x), "yMin": min(all_y), "xMax": max(all_x), "yMax": max(all_y),
            "outlineWidth": max(all_x) - min(all_x), "measurementVersion": 2,
        }
        svg_path = vectors / f"{glyph_name}.svg"
        width = max(1, round(bounds[2] * int(project.get("capHeight", 700)) / max(bounds[3], 1)))
        svg_paths = " ".join("M " + " L ".join(f"{x + left},{int(project.get('capHeight', 700)) - y}" for x, y in path) + " Z" for path in paths)
        svg_path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width + left * 2} {project.get("capHeight", 700)}"><path d="{svg_paths}"/></svg>\n', encoding="utf-8")
        compiled_count += 1
        compiled_sources.append(source)

    if compiled_count == 0:
        raise ValueError("No glyph images are ready to compile")

    feature_blocks = [str(style["featureCode"])] if style.get("featureCode") else []
    automatic_alternates = _automatic_contextual_alternates(compiled_sources)
    if automatic_alternates:
        feature_blocks.append(automatic_alternates)
    font.features.text = "\n\n".join(feature_blocks)

    ufo_path = output / f"{basename}.ufo"
    if ufo_path.exists():
        shutil.rmtree(ufo_path)
    font.save(ufo_path)
    ttfont = compileTTF(font, removeOverlaps=True)
    ttf_path = output / f"{basename}.ttf"
    ttfont.save(ttf_path)
    woff_path = output / f"{basename}.woff2"
    ttfont.flavor = "woff2"
    ttfont.save(woff_path)
    TTFont(ttf_path).close()
    TTFont(woff_path).close()
    css_path = output / f"{basename}.css"
    css_path.write_text(f'@font-face {{\n  font-family: "{family}";\n  src: url("./{woff_path.name}") format("woff2");\n  font-style: {style.get("fontStyle", "normal")};\n  font-weight: {style.get("fontWeight", 400)};\n  font-display: swap;\n}}\n', encoding="utf-8")
    archive = shutil.make_archive(str(output / basename), "zip", root_dir=output, base_dir=ufo_path.name)
    report_path = output / "validation-report.json"
    report_path.write_text(json.dumps({"success": True, "glyphCount": compiled_count + 2, "warnings": warnings}, indent=2), encoding="utf-8")
    return {"outputs": [str(ttf_path), str(woff_path), str(css_path), archive, str(report_path)], "warnings": warnings, "glyphCount": compiled_count + 2, "glyphBounds": glyph_bounds}
