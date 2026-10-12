from pathlib import Path
import io
import fitz
from PIL import Image
import pytesseract


def extract_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        doc = fitz.open(stream=content, filetype="pdf")
        parts = []
        for page in doc:
            text = page.get_text("text").strip()
            if len(text) < 30:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                try:
                    text = pytesseract.image_to_string(image).strip()
                except Exception:
                    # Keep parser usable when the OS-level Tesseract binary is not installed.
                    text = text or ""
            parts.append(text)
        return "\n\n".join(parts)
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
        image = Image.open(io.BytesIO(content))
        return pytesseract.image_to_string(image).strip()
    if suffix in {".txt", ".eml"}:
        return content.decode("utf-8", errors="replace")
    raise ValueError("Unsupported file type. Use PDF, image, TXT or EML.")
