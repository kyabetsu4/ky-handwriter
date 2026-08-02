from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def _decode_template(image: np.ndarray, definitions: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
    payload: dict[str, Any] | None = None
    if decoded:
        try:
            value = json.loads(decoded)
            if isinstance(value, dict) and value.get("format") == "handfont-template":
                payload = value
        except json.JSONDecodeError:
            pass
    if payload:
        match = next((item for item in definitions if item.get("id") == payload.get("templateId") and item.get("pageNumber") == payload.get("page")), None)
        if match:
            if match.get("checksum") != payload.get("checksum"):
                raise ValueError("Template QR checksum does not match the local project")
            return match, warnings
        raise ValueError("The scanned template does not belong to this project")
    if len(definitions) == 1:
        warnings.append("QR code was not readable; the project's only template page was selected")
        return definitions[0], warnings
    raise ValueError("Could not read the template QR code. A manual page selector is required for this image")


def _rectify(image: np.ndarray, definition: dict[str, Any]) -> tuple[np.ndarray, int]:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    corners, ids, _ = cv2.aruco.ArucoDetector(dictionary).detectMarkers(image)
    if ids is None:
        raise ValueError("No registration markers were detected")
    detected = {int(marker_id): marker_corners.reshape(4, 2) for marker_id, marker_corners in zip(ids.flatten(), corners)}
    source_points: list[np.ndarray] = []
    destination_points: list[np.ndarray] = []
    for marker in definition["markers"]:
        marker_id = int(marker["id"])
        if marker_id not in detected:
            continue
        x, y, size = float(marker["x"]), float(marker["y"]), float(marker["size"])
        source_points.extend(detected[marker_id])
        destination_points.extend(np.array([[x, y], [x + size, y], [x + size, y + size], [x, y + size]], dtype=np.float32))
    usable = len(source_points) // 4
    if usable < 3:
        raise ValueError(f"Only {usable} registration markers were usable; at least 3 are required")
    homography, _ = cv2.findHomography(np.array(source_points, dtype=np.float32), np.array(destination_points, dtype=np.float32), cv2.RANSAC, 4.0)
    if homography is None:
        raise ValueError("Could not calculate page alignment")
    page = definition["page"]
    rectified = cv2.warpPerspective(image, homography, (int(page["width"]), int(page["height"])), borderValue=(255, 255, 255))
    return rectified, usable


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def import_template(project_path: str, input_path: str, threshold: int = 160, import_mode: str = "standard") -> dict[str, Any]:
    root = Path(project_path).expanduser().resolve()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError("The selected template image was not found")
    if source.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("Template import currently supports PNG and JPEG images")
    project = json.loads((root / "project.json").read_text(encoding="utf-8"))
    definitions = [item for item in project.get("templates", []) if isinstance(item, dict) and item.get("cells")]
    if not definitions:
        raise ValueError("This project has no generated template definitions")
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The selected image could not be decoded")
    try:
        definition, warnings = _decode_template(image, definitions)
    except ValueError as qr_error:
        definition = next((item for item in definitions if re.search(rf"{re.escape(str(item['id']))}-page-{int(item['pageNumber'])}", source.stem, re.IGNORECASE)), None)
        warnings = []
        if definition:
            warnings.append("QR code was not readable; the template page was identified from its filename")
        else:
            try:
                provisional, _ = _rectify(image, definitions[0])
                definition, recovered_warnings = _decode_template(provisional, definitions)
                warnings.extend(recovered_warnings)
                warnings.append("QR code was decoded after registration-marker alignment")
            except ValueError:
                raise qr_error
    rectified, marker_count = _rectify(image, definition)
    purpose = str(definition.get("purpose", "standard"))
    if import_mode == "reimport" and purpose != "standard":
        raise ValueError("Choose one of this project's original completed template pages")
    if import_mode != "reimport" and purpose == "replacement":
        raise ValueError("Legacy replacement sheets cannot be used for an initial import")
    style_id = str(definition["styleId"])
    page_number = int(definition["pageNumber"])
    template_id = str(definition["id"])

    filled_dir = root / "sources" / "templates"
    glyph_dir = root / "sources" / "glyphs" / style_id
    filled_dir.mkdir(parents=True, exist_ok=True)
    glyph_dir.mkdir(parents=True, exist_ok=True)
    import_id = uuid.uuid4().hex[:8]
    filled_copy = filled_dir / f"{template_id}-page-{page_number}-filled-{import_id}{source.suffix.lower()}"
    shutil.copy2(source, filled_copy)
    normalized_path = filled_dir / f"{template_id}-page-{page_number}-normalized-{import_id}.png"
    cv2.imwrite(str(normalized_path), rectified)

    glyphs: list[dict[str, Any]] = []
    for cell in definition["cells"]:
        drawing = cell["drawingBounds"]
        x, y, width, height = (int(drawing[key]) for key in ("x", "y", "width", "height"))
        crop = rectified[y:y + height, x:x + width]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, int(threshold), 255, cv2.THRESH_BINARY_INV)
        channel_spread = crop.max(axis=2).astype(np.int16) - crop.min(axis=2).astype(np.int16)
        neutral_ink = np.where(channel_spread <= 30, 255, 0).astype(np.uint8)
        mask = cv2.bitwise_and(mask, neutral_ink)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        cleaned = np.zeros_like(mask)
        for index in range(1, count):
            if stats[index, cv2.CC_STAT_AREA] >= 8:
                cleaned[labels == index] = 255
        ink = int(cv2.countNonZero(cleaned))
        boundary = 5
        touches_boundary = bool(
            cv2.countNonZero(cleaned[:boundary, :]) or cv2.countNonZero(cleaned[-boundary:, :])
            or cv2.countNonZero(cleaned[:, :boundary]) or cv2.countNonZero(cleaned[:, -boundary:])
        )
        codepoint = int(cell["unicode"])
        suffix = f".alt{int(cell.get('variantIndex', 0)):02d}" if int(cell.get("variantIndex", 0)) else ""
        safe_stem = f"uni{codepoint:04X}{suffix}"
        original_path = glyph_dir / f"{safe_stem}.source.png"
        mask_path = glyph_dir / f"{safe_stem}.mask.png"
        cv2.imwrite(str(original_path), crop)
        cv2.imwrite(str(mask_path), cleaned)
        glyph_warnings: list[str] = []
        if ink < 30:
            status = "missing"
            glyph_warnings.append("No handwriting detected")
        else:
            status = "imported"
            if ink < 180:
                glyph_warnings.append("Very little ink was detected")
            if touches_boundary:
                glyph_warnings.append("Handwriting touches the extraction boundary")
        glyphs.append({
            "id": f"{style_id}_{safe_stem}", "glyphName": cell["glyphName"], "character": cell["character"], "unicode": codepoint if int(cell.get("variantIndex", 0)) == 0 else None,
            "sourceType": "template", "sourceImagePath": _relative(original_path, root), "processedImagePath": _relative(mask_path, root),
            "variantGroup": cell["glyphName"].split(".alt")[0] if int(cell.get("variantIndex", 0)) else None,
            "variantIndex": int(cell.get("variantIndex", 0)),
            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 0, "translateY": 0, "rotation": 0},
            "metrics": {"advanceWidth": 600, "leftSideBearing": 40, "rightSideBearing": 40},
            "processing": {"threshold": 200, "invert": False, "smoothing": 0, "despeckle": 2, "cropPadding": 12, "tracePreset": "preserve"},
            "status": status, "warnings": glyph_warnings,
            "templatePlacement": {"templateId": template_id, "pageNumber": page_number, "baselineY": int(cell["guides"]["baselineY"]) - y, "capHeightY": int(cell["guides"]["capHeightY"]) - y, "xHeightY": int(cell["guides"]["xHeightY"]) - y, "drawingBounds": drawing},
        })
    imported = sum(1 for glyph in glyphs if glyph["status"] == "imported")
    missing = len(glyphs) - imported
    return {
        "templateId": template_id, "pageNumber": page_number, "markerCount": marker_count,
        "filledSourcePath": _relative(filled_copy, root), "normalizedPagePath": _relative(normalized_path, root),
        "glyphs": glyphs, "importedCount": imported, "missingCount": missing, "warnings": warnings,
    }
