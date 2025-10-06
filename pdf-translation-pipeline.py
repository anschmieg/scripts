#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PDF FR→DE translation pipeline (coords-preserving):

1) Extract text with coordinates via MuPDF (`mutool draw -F json`).
2) Send text lines to an external translator (your tool/command), receive German lines back.
3) Render a translated overlay PDF at the exact same positions (bbox) with ReportLab.
4) (Optional) Remove original text with Ghostscript to avoid double text.
5) Merge overlay with the original/background using qpdf.

Safeguards:
- Dependency checks (mutool, qpdf; ghostscript optional).
- Subprocess timeouts + return-code checks.
- JSON schema validation for extracted layout.
- Font fallback + bbox-aware wrapping, auto font downscaling, ellipsis.
- Clear error messages and non-zero exit codes on failure.

Usage example:
    python pdf_translate_pipeline.py \
        --input input.pdf \
        --output translated.pdf \
        --translator-cmd "deepl_cli --from fr --to de --formality more --stdin --stdout" \
        --strip-text \
        --font-ttf /path/to/DejaVuSans.ttf \
        --abbr "DV=Vorderteil|VT" "DS=Rückenteil|RT" "MDV=vordere Mitte|VM" "MDS=hintere Mitte|HM" "CC=Seitennaht|SN" "CE=Schulternaht|SchN" "G=links|li." "D=rechts|re."
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

# ---------- Utilities ----------
import logging

# Simple logger setup
logger = logging.getLogger("pdfpipe")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def eprint(*args, **kwargs):
    """Compatibility wrapper: preserve existing eprint(...) call sites but route messages
    through the structured logger. Messages starting with known prefixes map to levels.
    """
    msg = " ".join(str(a) for a in args)
    # Allow passing 'exc_info' or other kwargs to logger
    if msg.startswith("[ERROR]") or msg.startswith("[ABORTED]"):
        logger.error(msg, **kwargs)
    elif msg.startswith("[WARN]") or msg.startswith("[WARNING]"):
        logger.warning(msg, **kwargs)
    elif msg.startswith("[CMD]") or msg.startswith("[STEP]") or msg.startswith("[OK]") or msg.startswith("[INFO]"):
        logger.info(msg, **kwargs)
    else:
        logger.info(msg, **kwargs)

def check_dep(name: str, required: bool = True) -> bool:
    path = shutil.which(name)
    if not path and required:
        eprint(f"[ERROR] Required dependency not found in PATH: {name}")
        sys.exit(2)
    return bool(path)

def run(cmd: List[str], timeout: int = 90, input_bytes: bytes = None, check: bool = True) -> subprocess.CompletedProcess:
    logger.info(f"[CMD] {' '.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.error(f"[ERROR] Command timed out after {timeout}s: {' '.join(cmd)}")
        sys.exit(3)
    if check and proc.returncode != 0:
        logger.error(f"[ERROR] Command failed ({proc.returncode}): {' '.join(cmd)}")
        logger.error(proc.stderr.decode("utf-8", errors="replace"))
        sys.exit(4)
    return proc

# ---------- Extraction ----------

@dataclass
class LineItem:
    page: int
    bbox: Tuple[float, float, float, float]
    font_size: float
    text: str
    id: str

# Legacy MuPDF JSON extractor removed; using stext.json-based extractor only.


def extract_layout_with_mutool_stext(pdf_path: str, timeout: int = 120):
    """
    Run mutool draw -F stext.json and parse the structured text JSON output.
    """
    cmd = ["mutool", "draw", "-F", "stext.json", "-o", "-", pdf_path]
    proc = run(cmd, timeout=timeout)
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except Exception as e:
        eprint("[ERROR] Failed to parse MuPDF stext.json:", e); sys.exit(5)
    if "pages" not in data:
        eprint("[ERROR] Bad stext.json"); sys.exit(6)
    return data


def extract_layout_with_mutool_json(pdf_path: str, timeout: int = 120) -> Dict:
    cmd = ["mutool", "draw", "-F", "json", "-o", "-", pdf_path]
    proc = run(cmd, timeout=timeout)
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except Exception as e:
        logger.error(f"[ERROR] Failed to parse MuPDF JSON: {e}")
        return {}
    return data


def mux_lines_from_mupdf_json(data: Dict) -> Tuple[List[LineItem], List[Tuple[float,float]]]:
    # Re-introduced minimal JSON mux as a robust fallback for older/alternate mutool output
    items: List[LineItem] = []
    pagesizes: List[Tuple[float, float]] = []

    if not data or 'pages' not in data:
        return items, pagesizes

    for p in data['pages']:
        num = int(p.get('number', 0)) or (len(pagesizes) + 1)
        w = float(p.get('width', 0) or 0)
        h = float(p.get('height', 0) or 0)
        if w == 0 or h == 0:
            logger.warning(f"[WARN] Page {num} missing width/height; defaulting to A4.")
            w, h = 595.2756, 841.8898
        pagesizes.append((w, h))

        for b in p.get('blocks', []):
            if b.get('type') != 'text':
                continue
            for ln in b.get('lines', []):
                spans = ln.get('spans', [])
                if not spans:
                    continue
                text = ''.join(s.get('text', '') for s in spans).strip()
                if not text:
                    continue
                try:
                    sizes = [float(s.get('size', 10)) for s in spans if 'size' in s]
                    font_size = sum(sizes)/len(sizes) if sizes else 10.0
                except Exception:
                    font_size = 10.0
                bbox = tuple(float(x) for x in ln.get('bbox', [0,0,0,0]))
                items.append(LineItem(page=num, bbox=bbox, font_size=font_size, text=text, id=f"p{num:03d}_l{len(items)+1:04d}"))
    return items, pagesizes


def mux_lines_from_stext(data: dict):
    items, pagesizes = [], []
    for p in data["pages"]:
        num = int(p.get("number", len(pagesizes)+1))
        w, h = float(p.get("width", 0)), float(p.get("height", 0))
        if not (w and h):
            w, h = 595.28, 841.89
        pagesizes.append((w,h))
        ln_no = 0
        for b in p.get("blocks", []):
            for ln in b.get("lines", []):
                spans = ln.get("spans", [])
                text = "".join(s.get("text","") for s in spans).strip()
                if not text: continue
                sizes = [float(s.get("size",10)) for s in spans if "size" in s] or [10.0]
                fsize = sum(sizes)/len(sizes)
                x0,y0,x1,y1 = [float(v) for v in ln.get("bbox",[0,0,0,0])]
                ln_no += 1
                items.append(LineItem(page=num, bbox=(x0,y0,x1,y1), font_size=fsize,
                                      text=text, id=f"p{num:03d}_l{ln_no:04d}"))
    # Do not exit here; return empty lists so caller can attempt OCR fallbacks.
    return items, pagesizes


def _sips_get_image_size(path: str):
    """Return (width, height) in pixels using macOS `sips` tool as a fallback when Pillow is not present."""
    try:
        proc = run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path], timeout=30, check=False)
        out = proc.stdout.decode("utf-8", errors="replace")
        w = h = None
        for line in out.splitlines():
            if line.strip().startswith("pixelWidth:"):
                w = int(line.split(':',1)[1].strip())
            if line.strip().startswith("pixelHeight:"):
                h = int(line.split(':',1)[1].strip())
        if w and h:
            return w, h
    except Exception:
        pass
    return None


def try_ocr_with_ocrmac(pdf_path: str, td: str, timeout: int = 300):
    """Attempt Apple-native OCR using the `ocrmac` package.
    Renders PDF pages to PNG via mutool, runs ocrmac.livetext on each image,
    converts annotations into LineItem objects.
    Returns (items, pagesizes) or ([], []) on failure/no-data.
    """
    try:
        from ocrmac import ocrmac
    except Exception:
        eprint("[INFO] ocrmac not available; skipping Apple Live Text OCR.")
        return [], []

    # Render pages to PNGs (300 DPI)
    imgs_dir = os.path.join(td, "ocr_images")
    os.makedirs(imgs_dir, exist_ok=True)
    cmd = ["mutool", "draw", "-r", "300", "-o", os.path.join(imgs_dir, "page_%03d.png"), pdf_path]
    run(cmd, timeout=timeout)

    pagesizes = load_pagesizes_from_pdf(pdf_path)
    items = []
    img_files = sorted([f for f in os.listdir(imgs_dir) if f.lower().endswith('.png')])
    if not img_files:
        eprint("[INFO] mutool produced no page images for OCR.")
        return [], []

    # Get PIL if available to read image size; otherwise use sips
    pil = None
    try:
        from PIL import Image
        pil = Image
    except Exception:
        pil = None

    for idx, img_fn in enumerate(img_files, start=1):
        img_path = os.path.join(imgs_dir, img_fn)
        # read image pixel size
        if pil:
            try:
                with pil.open(img_path) as im:
                    img_w, img_h = im.size
            except Exception:
                img_w = img_h = None
        else:
            r = _sips_get_image_size(img_path)
            if r:
                img_w, img_h = r
            else:
                img_w = img_h = None

        if img_w is None or img_h is None:
            eprint(f"[WARN] Couldn't determine image size for {img_path}; skipping page.")
            continue

        # recognize via ocrmac livetext — be resilient to different package APIs
        ocr = None
        annotations = None
        try:
            # Candidate 1: Simple text extraction
            if hasattr(ocrmac, 'text_from_image') and callable(getattr(ocrmac, 'text_from_image')):
                try:
                    text_result = ocrmac.text_from_image(img_path)
                    if text_result and isinstance(text_result, str) and text_result.strip():
                        # Create a simple annotation for the entire image
                        annotations = [{
                            'text': text_result.strip(),
                            'bbox': [0, 0, img_w, img_h]  # Full image bbox
                        }]
                        logger.debug(f"text_from_image returned text: {text_result[:100]}...")
                except Exception as e:
                    logger.debug(f"text_from_image failed: {e}")

            # Candidate 2: livetext_from_image - may return annotations directly
            if not annotations and hasattr(ocrmac, 'livetext_from_image'):
                try:
                    result = ocrmac.livetext_from_image(img_path)
                    if result:
                        # Check if it's already annotations
                        if isinstance(result, list) and result:
                            annotations = result
                            logger.debug(f"livetext_from_image returned {len(result)} annotations")
                        else:
                            # It's an OCR object, store for later processing
                            ocr = result
                except Exception as e:
                    logger.debug(f"livetext_from_image failed: {e}")

            # Candidate 3: OCR class
            if not annotations and not ocr and hasattr(ocrmac, 'OCR') and callable(getattr(ocrmac, 'OCR')):
                try:
                    ocr = ocrmac.OCR(img_path, framework="livetext")
                except Exception as e:
                    logger.debug(f"ocrmac.OCR(...) failed: {e}")

            # Candidate 4: submodule ocrmac.ocr.OCR
            if not annotations and not ocr and hasattr(ocrmac, 'ocr') and hasattr(ocrmac.ocr, 'OCR'):
                try:
                    ocr = ocrmac.ocr.OCR(img_path, framework="livetext")
                except Exception as e:
                    logger.debug(f"ocrmac.ocr.OCR(...) failed: {e}")

            # Candidate 5: other functions
            if not annotations and not ocr:
                if hasattr(ocrmac, 'live_text') and callable(getattr(ocrmac, 'live_text')):
                    try:
                        annotations = ocrmac.live_text(img_path)
                    except Exception as e:
                        logger.debug(f"ocrmac.live_text failed: {e}")
                elif hasattr(ocrmac, 'recognize_image') and callable(getattr(ocrmac, 'recognize_image')):
                    try:
                        annotations = ocrmac.recognize_image(img_path)
                    except Exception as e:
                        logger.debug(f"ocrmac.recognize_image failed: {e}")

            # If we obtained an OCR object, call its recognize-like method
            if ocr is not None and annotations is None:
                if hasattr(ocr, 'recognize') and callable(getattr(ocr, 'recognize')):
                    annotations = ocr.recognize()
                elif hasattr(ocr, 'run') and callable(getattr(ocr, 'run')):
                    annotations = ocr.run()
                elif callable(ocr):
                    # object may be a callable that returns annotations
                    annotations = ocr()

        except Exception as e:
            logger.debug(f"ocrmac general failure for {img_path}: {e}")

        if not annotations:
            # Log available attributes to help debugging the ocrmac installation
            available = sorted([a for a in dir(ocrmac) if not a.startswith('_')])
            logger.warning(f"[WARN] ocrmac did not return annotations for {img_path}. available attrs: {available}")
            return [], []

        # annotations expected to be iterable of objects/dicts with text and bbox
        page_width, page_height = pagesizes[idx-1] if idx-1 < len(pagesizes) else (595.28, 841.89)
        # Determine scaling between image pixels and PDF points.
        # mutool draw was invoked at -r 300 DPI; expected image pixels ~ page_pts * DPI / 72.
        dpi = 300.0
        exp_w_px = page_width * dpi / 72.0
        exp_h_px = page_height * dpi / 72.0
        # If the produced image appears rotated (width ~ expected height), swap axes.
        if abs(img_w - exp_h_px) < (0.05 * exp_h_px) and abs(img_h - exp_w_px) < (0.05 * exp_w_px):
            logger.debug(f"Detected rotated page image: img_w,img_h=({img_w},{img_h}) exp_w,exp_h=({exp_w_px:.1f},{exp_h_px:.1f})")
            # swap pixel dimensions so scale_x maps to page_width
            img_w, img_h = img_h, img_w
        # Compute scale from pixels -> PDF points
        scale_x = page_width / float(img_w)
        scale_y = page_height / float(img_h)

        ln_no = 0
        for ann in annotations:
            # support both dict and object with attributes, and ocrmac tuple format
            try:
                if isinstance(ann, tuple) and len(ann) >= 3:
                    # ocrmac format: (text, confidence, [x, y, w, h]) with normalized coords
                    txt = ann[0]
                    bbox_norm = ann[2]  # [x, y, w, h] in 0-1 range
                    if len(bbox_norm) >= 4:
                        x_norm, y_norm, w_norm, h_norm = bbox_norm[:4]
                        # Convert normalized coords to pixel coords
                        x0_px = x_norm * img_w
                        y0_px = y_norm * img_h
                        x1_px = (x_norm + w_norm) * img_w
                        y1_px = (y_norm + h_norm) * img_h
                        # Convert to PDF coords
                        x0 = x0_px * scale_x
                        x1 = x1_px * scale_x
                        y1 = page_height - (y0_px * scale_y)
                        y0 = page_height - (y1_px * scale_y)
                        bbox = [x0, y0, x1, y1]
                    else:
                        continue
                elif isinstance(ann, dict):
                    txt = ann.get('text') or ann.get('string') or ann.get('label') or ''
                    bbox = ann.get('bbox') or ann.get('bounding_box') or ann.get('rect')
                else:
                    txt = getattr(ann, 'text', '') or getattr(ann, 'string', '') or getattr(ann, 'label', '')
                    bbox = getattr(ann, 'bbox', None) or getattr(ann, 'bounding_box', None)
            except Exception:
                continue
            if not txt or not bbox:
                continue
            # Expect bbox as [x0,y0,x1,y1] in PDF points
            try:
                x0, y0, x1, y1 = [float(v) for v in bbox]
            except Exception:
                continue
            # approximate font size from bbox height
            fsize = max(8.0, (y1 - y0) * 0.8)
            ln_no += 1
            items.append(LineItem(page=idx, bbox=(x0, y0, x1, y1), font_size=fsize, text=txt.strip(), id=f"p{idx:03d}_l{ln_no:04d}"))

    if not items:
        return [], []
    return items, pagesizes


def try_ocr_with_ocrmypdf(pdf_path: str, td: str, timeout: int = 600):
    """Fallback OCR using ocrmypdf (external tool). Produces searchable PDF and re-parses it with mutool."""
    if not shutil.which('ocrmypdf'):
        eprint("[INFO] ocrmypdf not found; cannot fallback to ocrmypdf.")
        return [], []
    ocr_pdf = os.path.join(td, 'ocr.pdf')
    cmd = ["ocrmypdf", "--skip-text", pdf_path, ocr_pdf]
    run(cmd, timeout=timeout)
    if not os.path.exists(ocr_pdf) or os.path.getsize(ocr_pdf) == 0:
        eprint("[ERROR] ocrmypdf produced empty output.")
        return [], []
    # re-run mutool on the OCRed PDF
    layout = extract_layout_with_mutool_stext(ocr_pdf, timeout=120)
    items, pagesizes = mux_lines_from_stext(layout)
    return items, pagesizes

# ---------- Abbreviation replacement (optional) ----------

def parse_abbr_map(abbr_pairs: List[str]) -> Dict[str, Tuple[str, str]]:
    """
    abbr_pairs like: ["DV=Vorderteil|VT", "DS=Rückenteil|RT"]
    returns: {"DV": ("Vorderteil", "VT"), ...}
    """
    mapping = {}
    for p in abbr_pairs or []:
        if "=" not in p:
            eprint(f"[WARN] Bad --abbr entry (ignored): {p}")
            continue
        k, v = p.split("=", 1)
        full = v
        short = ""
        if "|" in v:
            full, short = v.split("|", 1)
        mapping[k.strip()] = (full.strip(), short.strip())
    return mapping

def apply_abbr_policy(text: str, abbr_map: Dict[str, Tuple[str,str]], prefer_full: bool = True) -> str:
    # Very conservative whole-word-ish replacement
    # (For diagrams/labels you may want a different strategy.)
    import re
    for fr, (full, short) in abbr_map.items():
        repl = full if prefer_full else (short or full)
        # Replace standalone tokens: DV, DS, MDV, etc.
        text = re.sub(rf"\b{re.escape(fr)}\b", repl, text)
    return text

# ---------- Translation ----------

def translate_lines_via_cmd(lines: List[str], translator_cmd: str, timeout: int = 180, mode: str = "lines") -> List[str]:
    """
    mode == "lines": Send newline-separated UTF-8 text to translator stdin.
                     Expect the same number of lines back (aligned).
    """
    if not translator_cmd:
        eprint("[ERROR] --translator-cmd is required.")
        sys.exit(8)

    # Prepare input: one line per source text (with trailing newline)
    payload = "\n".join(lines) + "\n"
    # Shell form to allow pipes/args in a single string:
    proc = run(["/bin/sh", "-lc", translator_cmd], timeout=timeout, input_bytes=payload.encode("utf-8"), check=False)

    if proc.returncode != 0:
        eprint("[ERROR] Translator command failed.")
        eprint(proc.stderr.decode("utf-8", errors="replace"))
        sys.exit(9)

    out = proc.stdout.decode("utf-8", errors="replace").splitlines()
    if len(out) != len(lines):
        eprint(f"[ERROR] Translator returned {len(out)} lines, expected {len(lines)}.")
        sys.exit(10)
    return out

# ---------- Overlay rendering ----------

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfReader

def load_pagesizes_from_pdf(pdf_path: str) -> List[Tuple[float,float]]:
    reader = PdfReader(pdf_path)
    sizes = []
    for p in reader.pages:
        box = p.mediabox
        sizes.append((float(box.width), float(box.height)))
    return sizes

def ensure_font(font_ttf: str = None, font_name: str = "OverlayFont") -> str:
    # If a TTF path is provided, register it; otherwise fall back to Helvetica.
    if font_ttf:
        if not os.path.exists(font_ttf):
            eprint(f"[ERROR] TTF font not found: {font_ttf}")
            sys.exit(11)
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_ttf))
            return font_name
        except Exception as e:
            eprint(f"[ERROR] Failed to register font '{font_ttf}': {e}")
            sys.exit(12)
    else:
        # Built-in: Helvetica (limited but generally handles umlauts)
        return "Helvetica"

def wrap_and_shrink(c, text: str, font_name: str, target_size: float, x0, y0, x1, y1,
                    min_size=8.0, line_spacing=1.18, padding=2.0) -> None:
    """
    Draw `text` inside bbox with word wrap.
    If it doesn't fit vertically, shrink font down to min_size.
    If still too tall, truncate last line with ellipsis.
    Coordinates: MuPDF uses bottom-left origin; ReportLab uses same.
    """
    def measure_width(s, size):
        return pdfmetrics.stringWidth(s, font_name, size)

    width = max(0.0, (x1 - x0) - 2 * padding)
    height = max(0.0, (y1 - y0) - 2 * padding)

    size = max(min_size, float(target_size))
    lines = []

    def wrap_at_size(sz: float) -> List[str]:
        words = text.split()
        out = []
        line = ""
        for w in words:
            test = (line + " " + w).strip()
            if measure_width(test, sz) <= width:
                line = test
            else:
                if line:
                    out.append(line)
                # If single word longer than width, hard-break it
                if measure_width(w, sz) > width:
                    seg = ""
                    for ch in w:
                        if measure_width(seg + ch, sz) <= width:
                            seg += ch
                        else:
                            out.append((seg or ch))
                            seg = ch
                    line = seg
                else:
                    line = w
        if line:
            out.append(line)
        return out

    # Try shrinking
    while size >= min_size:
        lines = wrap_at_size(size)
        line_height = size * line_spacing
        needed = len(lines) * line_height
        if needed <= height or len(lines) <= 1:
            break
        size -= 0.5

    # If still doesn't fit, truncate last line
    line_height = size * line_spacing
    max_lines = max(1, int(height // line_height))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            last = lines[-1]
            ell = "…"
            while measure_width(last + ell, size) > width and len(last) > 0:
                last = last[:-1]
            lines[-1] = (last + ell) if last else ell

    # Draw lines, top-down
    c.setFont(font_name, size)
    # ReportLab's origin is bottom-left; y increases upward
    y_top = y1 - padding
    y = y_top
    for ln in lines:
        y -= line_height
        if y < (y0 + padding - line_height):
            break
        c.drawString(x0 + padding, y, ln)

def render_overlay_pdf(input_pdf: str, items: List[LineItem], translated: List[str],
                       out_pdf: str, font_ttf: str = None, paint_white_bg: bool = True, min_size_override: float = None) -> None:
    if len(items) != len(translated):
        eprint("[ERROR] items vs translations length mismatch.")
        sys.exit(13)

    # Prefer reading sizes from original PDF (more reliable than mutool sizes)
    try:
        pagesizes = load_pagesizes_from_pdf(input_pdf)
    except Exception:
        eprint("[WARN] Falling back to mutool page sizes.")
        pages_by_num = max(i.page for i in items)
        pagesizes = [(595.2756, 841.8898)] * pages_by_num

    font_name = ensure_font(font_ttf, "OverlayFont")
    # Assemble by page
    from collections import defaultdict
    page_map = defaultdict(list)
    for it, de in zip(items, translated):
        page_map[it.page].append((it, de))

    # Create overlay
    c = None
    for pgnum, (w, h) in enumerate(pagesizes, start=1):
        if c is None:
            c = canvas.Canvas(out_pdf, pagesize=(w, h))
        else:
            c.setPageSize((w, h))
        # Place all lines for this page
        for it, de in page_map.get(pgnum, []):
            x0, y0, x1, y1 = it.bbox
            # Optional white wipe to hide FR text if we didn't strip text
            if paint_white_bg:
                c.setFillGray(1.0)
                c.rect(x0, y0, (x1 - x0), (y1 - y0), fill=1, stroke=0)
                c.setFillGray(0.0)
            # Draw translated line wrapped into same bbox
            wrap_and_shrink(
                c,
                de,
                font_name,
                target_size=it.font_size,
                x0=x0, y0=y0, x1=x1, y1=y1,
                min_size=(min_size_override if min_size_override is not None else max(7.5, it.font_size * 0.75)),
                line_spacing=1.18,
                padding=2.0,
            )
        c.showPage()
    if c:
        c.save()
    else:
        eprint("[ERROR] No pages rendered to overlay.")
        sys.exit(14)


def rasterize_pdf_to_png(pdf_path: str, out_dir: str, dpi: int = 150):
    """Render PDF pages to PNGs using mutool draw at given DPI into out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    cmd = ["mutool", "draw", "-r", str(dpi), "-o", os.path.join(out_dir, "page_%03d.png"), pdf_path]
    run(cmd, timeout=120)
    files = sorted([os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.endswith('.png')])
    return files


def image_similarity_score(img_a_path: str, img_b_path: str) -> float:
    """Return a simple similarity score between two images (0..1) using structural similarity (SSIM) if available, fallback to mean absolute difference."""
    try:
        from PIL import Image, ImageOps
        import numpy as np
    except Exception:
        return 0.0
    a = Image.open(img_a_path).convert('L')
    b = Image.open(img_b_path).convert('L')
    # resize to smallest common
    if a.size != b.size:
        b = b.resize(a.size)
    try:
        from skimage.metrics import structural_similarity as ssim
        arr_a = np.array(a, dtype=np.float32)
        arr_b = np.array(b, dtype=np.float32)
        s, _ = ssim(arr_a, arr_b, full=True)
        return float(s)
    except Exception:
        # fallback: 1 - normalized mean absolute error
        arr_a = np.array(a, dtype=np.float32)
        arr_b = np.array(b, dtype=np.float32)
        mae = float(np.mean(np.abs(arr_a - arr_b)))
        return max(0.0, 1.0 - (mae / 255.0))


def auto_tune_overlay(input_pdf: str, base_pdf: str, items: List[LineItem], translated: List[str], td: str, font_ttf: str, paint_white_bg: bool, debug_dir: str) -> Tuple[List[LineItem], float, float]:
    """Small grid search over merge_vtol and min_font to maximize similarity between overlay layer (raster) and original PDF raster.
    Returns (best_items, best_vtol, best_min_font).
    """
    # Search grid
    vtol_candidates = [6.0, 9.0, 12.0]
    minfont_candidates = [7.0, 8.0, 9.0]
    best_score = -1.0
    best_conf = (items, vtol_candidates[0], minfont_candidates[0])
    # Render original PDF at moderate DPI
    orig_dir = os.path.join(td, 'orig_raster')
    overlay_dir = os.path.join(td, 'overlay_raster')
    rasterize_pdf_to_png(input_pdf, orig_dir, dpi=150)
    for v in vtol_candidates:
        merged = merge_line_items(items, v_tol=v)
        # Render overlay with current minfont candidate later for each minfont
        for mf in minfont_candidates:
            # Render overlay PDF to a temporary file
            tmp_overlay = os.path.join(td, f'overlay_v{int(v)}_m{int(mf)}.pdf')
            render_overlay_pdf(input_pdf=base_pdf, items=merged, translated=translated, out_pdf=tmp_overlay, font_ttf=font_ttf, paint_white_bg=paint_white_bg)
            # Rasterize overlay
            overlay_subdir = os.path.join(overlay_dir, f'v{int(v)}_m{int(mf)}')
            rasterize_pdf_to_png(tmp_overlay, overlay_subdir, dpi=150)
            # Score first page similarity (fast heuristic)
            orig_img = sorted([os.path.join(orig_dir, f) for f in os.listdir(orig_dir) if f.endswith('.png')])[0]
            over_img = sorted([os.path.join(overlay_subdir, f) for f in os.listdir(overlay_subdir) if f.endswith('.png')])[0]
            score = image_similarity_score(orig_img, over_img)
            logger.info(f"[TUNE] v_tol={v} min_font={mf} score={score:.4f}")
            if score > best_score:
                best_score = score
                best_conf = (merged, v, mf)
    best_items, best_v, best_mf = best_conf
    logger.info(f"[TUNE] Best: v_tol={best_v} min_font={best_mf} score={best_score:.4f}")
    return best_items, best_v, best_mf


def merge_line_items(items: List[LineItem], v_tol: float = 6.0) -> List[LineItem]:
    """Merge nearby word-level LineItems into line-level items using vertical proximity.
    v_tol is vertical tolerance in PDF points for grouping words into the same line.
    This is a lightweight heuristic to reduce overlay clutter when OCR produces many word boxes.
    """
    from collections import defaultdict
    pages = defaultdict(list)
    for it in items:
        pages[it.page].append(it)

    out: List[LineItem] = []
    for page, its in pages.items():
        # compute vertical center for sorting (top->bottom)
        def center_y(i: LineItem):
            y0, y1 = i.bbox[1], i.bbox[3]
            return (y0 + y1) / 2.0

        its_sorted = sorted(its, key=lambda i: -center_y(i))
        # Precompute median word width to decide gap thresholds
        widths = []
        for it in its_sorted:
            widths.append(max(1.0, it.bbox[2] - it.bbox[0]))
        median_w = sorted(widths)[len(widths)//2] if widths else 50.0

        groups: List[List[LineItem]] = []
        for it in its_sorted:
            if not groups:
                groups.append([it])
                continue
            grp = groups[-1]
            # compare vertical center to group's average center
            grp_centers = [(g.bbox[1] + g.bbox[3]) / 2.0 for g in grp]
            grp_center = sum(grp_centers) / len(grp_centers)
            if abs(center_y(it) - grp_center) <= v_tol:
                # now check horizontal adjacency: do not join across very large gaps
                # compute gap between this item and the rightmost item in grp
                rightmost = max(g.bbox[2] for g in grp)
                gap = it.bbox[0] - rightmost
                # threshold: either a few times median word width or a fraction of page width
                gap_thresh = max(median_w * 1.5, (pages[page][0].bbox[2] - pages[page][0].bbox[0]) * 0.20 if pages[page] else 100)
                if gap <= gap_thresh:
                    grp.append(it)
                else:
                    # large horizontal gap — start a new group (likely column/table separation)
                    groups.append([it])
            else:
                groups.append([it])

        # Merge each group into a single LineItem by ordering left->right and preserving bounds
        for grp in groups:
            grp_sorted = sorted(grp, key=lambda i: i.bbox[0])
            texts = [g.text for g in grp_sorted if g.text]
            if not texts:
                continue
            full_text = " ".join(t.strip() for t in texts if t.strip())
            x0 = min(g.bbox[0] for g in grp_sorted)
            y0 = min(g.bbox[1] for g in grp_sorted)
            x1 = max(g.bbox[2] for g in grp_sorted)
            y1 = max(g.bbox[3] for g in grp_sorted)
            # Constrain group width: if it spans more than 90% of page, try splitting by large internal gaps
            page_w = pages[page][0].bbox[2] - pages[page][0].bbox[0] if pages[page] else (x1 - x0)
            if (x1 - x0) / page_w > 0.9 and len(grp_sorted) > 2:
                # split at largest internal gap
                gaps = []
                for a, b in zip(grp_sorted, grp_sorted[1:]):
                    gaps.append((b.bbox[0] - a.bbox[2], a, b))
                # find largest gap index
                gaps_sorted = sorted(gaps, key=lambda x: -x[0])
                if gaps_sorted and gaps_sorted[0][0] > max(median_w * 2.0, page_w * 0.25):
                    # split into two groups at that gap
                    split_at = gaps.index(gaps_sorted[0]) + 1
                    left = grp_sorted[:split_at]
                    right = grp_sorted[split_at:]
                    for part in (left, right):
                        px0 = min(g.bbox[0] for g in part)
                        py0 = min(g.bbox[1] for g in part)
                        px1 = max(g.bbox[2] for g in part)
                        py1 = max(g.bbox[3] for g in part)
                        ptext = " ".join(g.text.strip() for g in part if g.text)
                        pfsize = max(g.font_size for g in part)
                        out.append(LineItem(page=page, bbox=(px0, py0, px1, py1), font_size=pfsize, text=ptext,
                                            id=f"p{page:03d}_merged_{len(out)+1:04d}"))
                    continue
            fsize = max(g.font_size for g in grp_sorted)
            out.append(LineItem(page=page, bbox=(x0, y0, x1, y1), font_size=fsize, text=full_text,
                                id=f"p{page:03d}_merged_{len(out)+1:04d}"))

    # Keep original order by page then y(top->bottom) then x
    out_sorted = sorted(out, key=lambda i: (i.page, -((i.bbox[1] + i.bbox[3]) / 2.0), i.bbox[0]))
    return out_sorted

# ---------- Main Orchestration ----------

def main():
    ap = argparse.ArgumentParser(description="FR→DE PDF translator (coords preserved).")
    ap.add_argument("--input", required=True, help="Input PDF (French).")
    ap.add_argument("--output", required=True, help="Output PDF (German).")
    ap.add_argument("--translator-cmd", required=True,
                    help="Shell command that reads UTF-8 lines on stdin and outputs the same number of translated lines on stdout.")
    ap.add_argument("--strip-text", action="store_true",
                    help="Use Ghostscript to remove original text (cleaner result).")
    ap.add_argument("--font-ttf", default=None,
                    help="Path to a TTF font supporting German diacritics (e.g., DejaVuSans.ttf).")
    ap.add_argument("--timeout", type=int, default=120, help="Timeout (s) for each external tool.")
    ap.add_argument("--prefer-full-terms", action="store_true",
                    help="When replacing abbreviations in extracted text before translation, prefer full German terms.")
    ap.add_argument("--abbr", nargs="*", default=[],
                    help="French=GermanFull|GermanShort mappings. Example: DV=Vorderteil|VT MDV='vordere Mitte|VM'")
    ap.add_argument("--debug-dir", default=None,
                    help="If set, keep temporary artifacts (stext.json, OCR images, overlay) in this directory for inspection.")
    ap.add_argument("--paint-white", action="store_true",
                    help="Paint white rectangles behind translated text (default: off).")
    ap.add_argument("--merge-vtol", type=float, default=6.0,
                    help="Vertical tolerance (pts) for merging OCR word boxes into lines. Larger values produce fewer, longer lines.")
    ap.add_argument("--min-font", type=float, default=7.5,
                    help="Minimum font size (pts) when shrinking text to fit a bbox.")
    ap.add_argument("--auto-tune", action="store_true",
                    help="Run a small grid search over merge_vtol/min-font to improve overlay alignment (slow).")
    args = ap.parse_args()

    # Check deps
    have_mutool = check_dep("mutool", required=True)
    have_qpdf = check_dep("qpdf", required=True)
    have_gs = check_dep("gs", required=False)

    if args.strip_text and not have_gs:
        eprint("[WARN] --strip-text requested but Ghostscript not found; proceeding without stripping original text.")
        args.strip_text = False

    if not os.path.exists(args.input):
        eprint(f"[ERROR] Input not found: {args.input}")
        sys.exit(15)

    abbr_map = parse_abbr_map(args.abbr)

    # Prepare temporary directory (optionally persistent for debugging)
    if args.debug_dir:
        td = os.path.abspath(args.debug_dir)
        os.makedirs(td, exist_ok=True)
        _td_obj = None
        logger.info(f"[INFO] Debug dir requested; keeping temp artifacts in {td}")
    else:
        _td_obj = tempfile.TemporaryDirectory()
        td = _td_obj.name

    try:
        eprint("[STEP] Extracting text + coordinates with MuPDF (stext.json) …")
        layout_json = extract_layout_with_mutool_stext(args.input, timeout=args.timeout)
        # Save stext.json for diagnostics
        try:
            stext_path = os.path.join(td, 'layout.stext.json')
            with open(stext_path, 'w', encoding='utf-8') as fh:
                json.dump(layout_json, fh, ensure_ascii=False, indent=2)
            logger.info(f"[INFO] Saved stext.json to {stext_path} for inspection.")
        except Exception as e:
            logger.debug(f"Failed to save stext.json: {e}")

        items, _sizes = mux_lines_from_stext(layout_json)
        if not items:
            logger.info("[INFO] No embedded text found in stext.json; attempting OCR fallbacks...")
            # Try Apple Live Text via ocrmac first
            oitems, osizes = try_ocr_with_ocrmac(args.input, td, timeout=max(120, args.timeout))
            if oitems:
                items, _sizes = oitems, osizes
                logger.info(f"[OK] OCR via ocrmac produced {len(items)} item(s).")
                # Merge many small OCR word boxes into line-level items for cleaner overlays
                if len(items) > 300:
                    merged = merge_line_items(items, v_tol=args.merge_vtol)
                    logger.info(f"[INFO] Merged OCR items -> {len(merged)} line(s) (v_tol={args.merge_vtol}).")
                    items = merged
            else:
                # Fallback: ocrmypdf -> re-parse
                oitems, osizes = try_ocr_with_ocrmypdf(args.input, td, timeout=max(300, args.timeout))
                if oitems:
                    items, _sizes = oitems, osizes
                    logger.info(f"[OK] OCR via ocrmypdf produced {len(items)} item(s).")
                    if len(items) > 300:
                        merged = merge_line_items(items, v_tol=args.merge_vtol)
                        logger.info(f"[INFO] Merged OCR items -> {len(merged)} line(s) (v_tol={args.merge_vtol}).")
                        items = merged
                else:
                    logger.error("[ERROR] No text lines found after OCR attempts.")
                    sys.exit(7)
        eprint(f"[OK] Extracted {len(items)} line(s).")

        # 2) Prepare lines (apply optional abbr replacement pre-translation)
        src_lines = []
        for it in items:
            txt = it.text
            if abbr_map:
                txt = apply_abbr_policy(txt, abbr_map, prefer_full=args.prefer_full_terms)
            src_lines.append(txt)

        # 3) Translate
        eprint("[STEP] Translating lines via external command …")
        translated = translate_lines_via_cmd(src_lines, translator_cmd=args.translator_cmd, timeout=max(180, args.timeout))
        eprint("[OK] Translation received.")

        # 4) Optional text strip → background.pdf
        base_pdf = args.input
        if args.strip_text:
            eprint("[STEP] Stripping original text with Ghostscript …")
            bg_pdf = os.path.join(td, "background.pdf")
            # FILTERTEXT removes all selectable text; keeps vector/images.
            cmd = ["gs", "-o", bg_pdf, "-sDEVICE=pdfwrite", "-dFILTERTEXT", args.input]
            run(cmd, timeout=max(180, args.timeout))
            if not os.path.exists(bg_pdf) or os.path.getsize(bg_pdf) == 0:
                eprint("[ERROR] Ghostscript produced an empty background.")
                sys.exit(16)
            base_pdf = bg_pdf
            eprint("[OK] background.pdf ready.")

        # 5) Build overlay.pdf
        eprint("[STEP] Rendering overlay PDF at exact coordinates …")
        overlay_pdf = os.path.join(td, "overlay.pdf")
        # Paint white boxes only if requested explicitly OR if we stripped original text
        paint_white = args.paint_white or args.strip_text

        # Optionally run auto-tune to select merge_vtol and min font
        chosen_min_font = None
        if args.auto_tune:
            logger.info("[INFO] Running auto-tune to pick merge_vtol/min-font (this may be slow)")
            tuned_items, best_v, best_mf = auto_tune_overlay(args.input, base_pdf, items, translated, td, args.font_ttf, paint_white, td)
            items = tuned_items
            chosen_min_font = best_mf

        render_overlay_pdf(input_pdf=base_pdf, items=items, translated=translated,
                           out_pdf=overlay_pdf, font_ttf=args.font_ttf, paint_white_bg=paint_white, min_size_override=chosen_min_font)
        if not os.path.exists(overlay_pdf) or os.path.getsize(overlay_pdf) == 0:
            eprint("[ERROR] Overlay generation failed.")
            sys.exit(17)
        eprint("[OK] overlay.pdf ready.")

        # 6) Merge overlay → final
        eprint("[STEP] Merging overlay with base using qpdf …")
        cmd = ["qpdf", "--overlay", overlay_pdf, "--", base_pdf, args.output]
        run(cmd, timeout=args.timeout)
        if not os.path.exists(args.output) or os.path.getsize(args.output) == 0:
            eprint("[ERROR] Final merge produced an empty file.")
            sys.exit(18)

        eprint(f"[DONE] Wrote: {args.output}")
    finally:
        # Clean up if we created a temporary directory object
        try:
            if '_td_obj' in locals() and _td_obj is not None:
                _td_obj.cleanup()
        except Exception:
            pass

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        eprint("\n[ABORTED] Interrupted by user.")
        sys.exit(130)
