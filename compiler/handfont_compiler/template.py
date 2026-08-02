from __future__ import annotations

import hashlib
import io
import json
import math
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


PAGE_PRESETS = {
    "a4-portrait": (2480, 3508, "A4", "portrait"),
    "letter-portrait": (2550, 3300, "US Letter", "portrait"),
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ["C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf", "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _reference_font_for_cap_height(cap_height: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = "C:/Windows/Fonts/calibri.ttf"
    try:
        probe = ImageFont.truetype(font_path, 1000)
        bounds = probe.getbbox("H", anchor="ls")
        measured_cap_height = max(1, bounds[3] - bounds[1])
        size = max(1, round(cap_height * 1000 / measured_cap_height))
        return ImageFont.truetype(font_path, size)
    except OSError:
        return _font(cap_height)


def _aruco(marker_id: int, size: int) -> Image.Image:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    pixels = cv2.aruco.generateImageMarker(dictionary, marker_id, size)
    return Image.fromarray(pixels).convert("RGB")


def _glyph_name(character: str, variant: int) -> str:
    base = character if character.isascii() and character.isalpha() else f"uni{ord(character):04X}"
    return base if variant == 0 else f"{base}.alt{variant:02d}"


def generate_template(project_path: str, style_id: str, characters: str, preset: str = "a4-portrait", variants: int = 1, reference_letters: bool = True, requested_glyphs: list[dict[str, Any]] | None = None, purpose: str = "standard") -> dict[str, Any]:
    root = Path(project_path).expanduser().resolve()
    project = json.loads((root / "project.json").read_text(encoding="utf-8"))
    if preset not in PAGE_PRESETS:
        raise ValueError(f"Unsupported page preset: {preset}")
    width, height, page_name, orientation = PAGE_PRESETS[preset]
    chars = list(dict.fromkeys(characters))
    if requested_glyphs:
        expanded = [{"character": str(item["character"]), "variantIndex": int(item.get("variantIndex", 0)), "glyphName": str(item["glyphName"])} for item in requested_glyphs]
    else:
        expanded = [{"character": char, "variantIndex": variant, "glyphName": _glyph_name(char, variant)} for char in chars for variant in range(variants)]
    if not expanded:
        raise ValueError("At least one character is required")
    columns = 4
    rows = 7
    per_page = columns * rows
    total_pages = math.ceil(len(expanded) / per_page)
    template_id = f"tmpl_{uuid.uuid4().hex[:12]}"
    marker_size = 116
    margin_x, top, bottom, gap = 170, 330, 170, 24
    grid_width = width - margin_x * 2
    grid_height = height - top - bottom
    cell_width = (grid_width - gap * (columns - 1)) // columns
    cell_height = (grid_height - gap * (rows - 1)) // rows
    output_dir = root / "sources" / "templates"
    definition_dir = root / "templates"
    output_dir.mkdir(parents=True, exist_ok=True)
    definition_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []
    definitions: list[dict[str, Any]] = []

    for page_index in range(total_pages):
        page_number = page_index + 1
        page_cells = expanded[page_index * per_page:(page_index + 1) * per_page]
        payload_base = {"format": "handfont-template", "version": 1, "templateId": template_id, "projectId": project["id"], "styleId": style_id, "page": page_number, "purpose": purpose}
        checksum = hashlib.sha256(json.dumps(payload_base, sort_keys=True).encode()).hexdigest()[:16]
        payload = {**payload_base, "checksum": checksum}
        cells: list[dict[str, Any]] = []
        for index, requested in enumerate(page_cells):
            character = requested["character"]
            variant = requested["variantIndex"]
            row, column = divmod(index, columns)
            x = margin_x + column * (cell_width + gap)
            y = top + row * (cell_height + gap)
            inset_x, label_height = 30, 58
            drawing = {"x": x + inset_x, "y": y + label_height, "width": cell_width - inset_x * 2, "height": cell_height - label_height - 22}
            baseline_y = drawing["y"] + round(drawing["height"] * 0.78)
            cells.append({
                "index": page_index * per_page + index,
                "character": character,
                "unicode": ord(character),
                "glyphName": requested["glyphName"],
                "variantIndex": variant,
                "bounds": {"x": x, "y": y, "width": cell_width, "height": cell_height},
                "drawingBounds": drawing,
                "guides": {
                    "ascenderY": drawing["y"] + round(drawing["height"] * 0.08),
                    "capHeightY": drawing["y"] + round(drawing["height"] * 0.18),
                    "xHeightY": drawing["y"] + round(drawing["height"] * 0.42),
                    "baselineY": baseline_y,
                    "descenderY": drawing["y"] + round(drawing["height"] * 0.94),
                },
            })
        definition = {
            "id": template_id, "version": 1, "projectId": project["id"], "styleId": style_id, "purpose": purpose,
            "pageNumber": page_number, "totalPages": total_pages,
            "page": {"width": width, "height": height, "unit": "px", "dpi": 300, "name": page_name, "orientation": orientation},
            "grid": {"rows": rows, "columns": columns, "x": margin_x, "y": top, "width": grid_width, "height": grid_height, "gapX": gap, "gapY": gap},
            "markers": [
                {"id": 10, "corner": "top-left", "x": 38, "y": 38, "size": marker_size},
                {"id": 11, "corner": "top-right", "x": width - 38 - marker_size, "y": 38, "size": marker_size},
                {"id": 12, "corner": "bottom-right", "x": width - 38 - marker_size, "y": height - 38 - marker_size, "size": marker_size},
                {"id": 13, "corner": "bottom-left", "x": 38, "y": height - 38 - marker_size, "size": marker_size},
            ],
            "cells": cells, "checksum": checksum,
            "referenceLetters": {"enabled": reference_letters, "font": "Calibri", "color": "#d3d6da"},
        }
        definition_path = definition_dir / f"{template_id}-page-{page_number}.json"
        definition_path.write_text(json.dumps(definition, indent=2, ensure_ascii=False), encoding="utf-8")
        definitions.append(definition)

        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        draw.text((margin_x, 88), project["familyName"], fill="#161616", font=_font(48, True))
        draw.text((margin_x, 155), f"Handwriting template  /  {style_id}  /  page {page_number} of {total_pages}", fill="#666a70", font=_font(25))
        draw.text((margin_x, 212), "Write in black. Keep each character inside its box.", fill="#666a70", font=_font(22))
        for marker in definition["markers"]:
            image.paste(_aruco(marker["id"], marker_size), (marker["x"], marker["y"]))
        qr_size = 230
        qr = qrcode.make(json.dumps(payload, separators=(",", ":"))).convert("RGB").resize((qr_size, qr_size), Image.Resampling.NEAREST)
        image.paste(qr, (width - margin_x - qr_size, 64))
        for cell in cells:
            bounds, drawing = cell["bounds"], cell["drawingBounds"]
            draw.rounded_rectangle((bounds["x"], bounds["y"], bounds["x"] + bounds["width"], bounds["y"] + bounds["height"]), radius=12, outline="#b8bdc2", width=3)
            label = cell["character"] + (f"  form {cell['variantIndex'] + 1}" if requested_glyphs or variants > 1 else "")
            draw.text((bounds["x"] + 18, bounds["y"] + 13), label, fill="#30343a", font=_font(23, True))
            guides = cell["guides"]
            for name in ("capHeightY", "xHeightY", "baselineY", "descenderY"):
                color = "#8ca6bc" if name == "baselineY" else "#cddce8"
                line_width = 3 if name == "baselineY" else 2
                draw.line((drawing["x"], guides[name], drawing["x"] + drawing["width"], guides[name]), fill=color, width=line_width)
            if reference_letters:
                reference_cap_height = guides["baselineY"] - guides["capHeightY"]
                draw.text(
                    (drawing["x"] + drawing["width"] // 2, guides["baselineY"]),
                    cell["character"], fill="#d3d6da", font=_reference_font_for_cap_height(reference_cap_height), anchor="ms"
                )
        png_path = output_dir / f"{template_id}-page-{page_number}.png"
        image.save(png_path, dpi=(300, 300))

        pdf_path = output_dir / f"{template_id}-page-{page_number}.pdf"
        page_width_pt, page_height_pt = width * 72 / 300, height * 72 / 300
        pdf = canvas.Canvas(str(pdf_path), pagesize=(page_width_pt, page_height_pt), pageCompression=1)
        pdf.drawImage(ImageReader(image), 0, 0, width=page_width_pt, height=page_height_pt, mask="auto")
        pdf.showPage(); pdf.save()
        outputs.extend([str(png_path), str(pdf_path), str(definition_path)])

    return {"outputs": outputs, "templates": definitions, "templateId": template_id, "pageCount": total_pages, "warnings": []}
