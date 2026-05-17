"""
Contract Parser — T4.1 (Người C)

Parses contract documents (PDF, DOCX, TXT) to Markdown using MinerU CLI,
with PII detection and redaction for Vietnamese contracts.

Usage:
    from contract import ContractParser

    parser = ContractParser()
    contract = parser.parse("path/to/contract.pdf")
    print(contract.redacted_text)
"""
from __future__ import annotations

import os
import base64
import subprocess
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from src.config import CONTRACT_OCR_MAX_PAGES, CONTRACT_OCR_MIN_TEXT_CHARS, OPENAI_OCR_MODEL
from .models import Contract, ParseError
from .pii import detect_pii, redact_pii


SUPPORTED_FORMATS = {".pdf", ".docx", ".txt", ".md"}

_VIETNAMESE_CHARS = set("ăâđêôơưĂÂĐÊÔƠƯáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
_MOJIBAKE_MARKERS = ("Ã", "Ä", "Å", "Æ", "Ç", "È", "É", "Ê", "Ë", "Ð", "Ñ", "Ò", "Ó", "Ô", "Õ", "Ö", "×", "Ø", "Ù", "Ú", "á»", "áº", "Ä")


def repair_mojibake_text(text: str) -> str:
    """Repair common UTF-8-as-Latin-1 mojibake when the candidate is clearly better."""
    if not text:
        return text

    candidates = [text]
    for source_encoding in ("latin-1", "cp1252"):
        try:
            candidates.append(text.encode(source_encoding).decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue

    return max(candidates, key=_text_quality_score)


def _text_quality_score(text: str) -> int:
    score = 0
    score += sum(3 for ch in text if ch in _VIETNAMESE_CHARS)
    score -= sum(2 for marker in _MOJIBAKE_MARKERS for _ in range(text.count(marker)))
    score -= text.count("\ufffd") * 5
    return score


class ContractParser:
    """
    Parse contract documents to Markdown with PII redaction.

    Uses MinerU CLI for document parsing (PDF/DOCX/TXT → Markdown).
    Automatically detects and redacts Vietnamese PII.
    """

    def __init__(
        self,
        output_dir: Optional[str] = None,
        lang: str = "ch",  # MinerU uses "ch" for Chinese/Vietnamese OCR
        backend: str = "pipeline",
    ) -> None:
        """
        Initialize ContractParser.

        Args:
            output_dir: Temporary output directory for MinerU (auto-created if None)
            lang: OCR language code for MinerU
            backend: MinerU backend ("pipeline" for CPU, "vlm-auto-engine" for GPU)
        """
        self._output_dir = output_dir
        self._lang = lang
        self._backend = backend

    def parse(
        self,
        file_path: str,
        do_redact_pii: bool = True,
    ) -> Contract:
        """
        Parse a contract document.

        Args:
            file_path: Path to PDF, DOCX, or TXT file
            do_redact_pii: Whether to detect and redact PII (default: True)

        Returns:
            Contract object with raw_text, redacted_text, and pii_map

        Raises:
            ParseError: If parsing fails
        """
        path = Path(file_path)

        # Validate file exists
        if not path.exists():
            raise ParseError(
                f"File not found: {file_path}",
                file_path=file_path,
                error_type="unknown",
            )

        # Validate format
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_FORMATS:
            raise ParseError(
                f"Unsupported format: {suffix}. Supported: {SUPPORTED_FORMATS}",
                file_path=file_path,
                error_type="unsupported",
            )

        # Parse based on format
        if suffix in {".txt", ".md"}:
            raw_text = self._read_txt(path)
        elif suffix == ".pdf":
            raw_text = self._read_pdf_text_or_ocr(path)
        else:
            # Parse with MinerU for PDF/DOCX
            try:
                raw_text = self._run_mineru(path)
            except ParseError:
                raise
            except Exception as e:
                raise ParseError(
                    f"MinerU parsing failed: {str(e)}",
                    file_path=file_path,
                    error_type="unknown",
                    original_exception=e,
                )

        raw_text = self._normalize_text(raw_text)

        # PII detection and redaction
        pii_matches = detect_pii(raw_text) if do_redact_pii else []
        redacted_text, pii_map = redact_pii(raw_text, pii_matches) if do_redact_pii else (raw_text, {})

        return Contract(
            id=str(uuid.uuid4()),
            raw_text=raw_text,
            redacted_text=redacted_text,
            source_format=suffix.lstrip("."),
            upload_date=date.today(),
            pii_map=pii_map,
            metadata={
                "file_size": path.stat().st_size,
                "file_name": path.name,
            },
        )

    def _read_txt(self, path: Path) -> str:
        """
        Read TXT file directly without MinerU.

        Args:
            path: Path to TXT file

        Returns:
            Text content

        Raises:
            ParseError: If reading fails
        """
        try:
            raw_bytes = path.read_bytes()
            for encoding in ("utf-8", "utf-8-sig", "cp1258", "latin-1"):
                try:
                    return repair_mojibake_text(raw_bytes.decode(encoding))
                except UnicodeDecodeError:
                    continue
            raise UnicodeDecodeError("unknown", raw_bytes, 0, 1, "Could not decode text file")
        except Exception as e:
            raise ParseError(
                f"Failed to read TXT file: {str(e)}",
                file_path=str(path),
                error_type="corrupted",
                original_exception=e,
            )

    def _read_pdf_text_or_ocr(self, path: Path) -> str:
        """
        Extract text from PDF text layer first. OCR only pages with too little text.
        """
        try:
            import fitz  # PyMuPDF
        except Exception as e:
            raise ParseError(
                "PyMuPDF is required for PDF parsing. Install pymupdf.",
                file_path=str(path),
                error_type="unsupported",
                original_exception=e,
            )

        try:
            doc = fitz.open(path)
        except Exception as e:
            raise ParseError(
                f"Failed to open PDF: {str(e)}",
                file_path=str(path),
                error_type="corrupted",
                original_exception=e,
            )

        parts: list[str] = []
        try:
            for page_index, page in enumerate(doc):
                text = page.get_text("text").strip()
                if len(text) >= CONTRACT_OCR_MIN_TEXT_CHARS:
                    parts.append(text)
                    continue

                if page_index >= CONTRACT_OCR_MAX_PAGES:
                    parts.append(text)
                    continue

                png_bytes = self._render_pdf_page_png(page)
                parts.append(self._ocr_image_with_openai(png_bytes, page_index + 1))
        finally:
            doc.close()

        return "\n\n".join(part for part in parts if part.strip())

    def _render_pdf_page_png(self, page) -> bytes:
        import fitz
        matrix = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png")

    def _ocr_image_with_openai(self, image_bytes: bytes, page_number: int) -> str:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ParseError(
                "OPENAI_API_KEY is required for OCR fallback",
                error_type="ocr_failure",
            )

        from openai import OpenAI

        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        base_url = (os.getenv("OPENAI_BASE_URL") or "").strip() or "https://api.openai.com/v1"
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
        response = client.chat.completions.create(
            model=OPENAI_OCR_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "OCR trang hợp đồng này sang Markdown/plain text tiếng Việt. "
                                "Giữ thứ tự điều khoản, số điều, khoản, điểm. "
                                "Chỉ trả về nội dung OCR, không giải thích."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or ""
        return f"\n\n<!-- OCR page {page_number} -->\n{content.strip()}"

    def _normalize_text(self, text: str) -> str:
        lines = [line.rstrip() for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        normalized = "\n".join(lines)
        while "\n\n\n" in normalized:
            normalized = normalized.replace("\n\n\n", "\n\n")
        return normalized.strip()

    def _run_mineru(self, path: Path) -> str:
        """
        Run MinerU CLI to parse document to Markdown.

        Args:
            path: Path to document

        Returns:
            Markdown text output

        Raises:
            ParseError: If MinerU fails
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [
                "mineru",
                "--path", str(path),
                "--output", tmpdir,
                "--lang", self._lang,
                "--backend", self._backend,
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                )
            except subprocess.TimeoutExpired:
                raise ParseError(
                    "MinerU parsing timed out (5 minutes)",
                    file_path=str(path),
                    error_type="ocr_failure",
                )
            except Exception as e:
                raise ParseError(
                    f"Failed to run MinerU: {str(e)}",
                    file_path=str(path),
                    error_type="unknown",
                    original_exception=e,
                )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or "MinerU exited with non-zero code"
                raise ParseError(
                    f"MinerU error: {error_msg}",
                    file_path=str(path),
                    error_type="ocr_failure",
                )

            # Read output Markdown
            md_content = self._read_mineru_output(tmpdir, path)
            return md_content

    def _read_mineru_output(self, tmpdir: str, path: Path) -> str:
        """
        Read MinerU output Markdown from temp directory.

        MinerU outputs to: {tmpdir}/{filename_without_ext}/{filename}.md

        Args:
            tmpdir: Temporary directory used by MinerU
            path: Original file path

        Returns:
            Markdown content

        Raises:
            ParseError: If output not found
        """
        # MinerU creates a subdirectory with the filename (without extension)
        stem = path.stem
        output_dir = os.path.join(tmpdir, stem)

        if not os.path.exists(output_dir):
            # Try listing what's in tmpdir
            contents = os.listdir(tmpdir)
            if contents:
                output_dir = os.path.join(tmpdir, contents[0])
            else:
                raise ParseError(
                    "MinerU produced no output",
                    file_path=str(path),
                    error_type="ocr_failure",
                )

        # Find .md file
        md_files = [f for f in os.listdir(output_dir) if f.endswith(".md")]
        if not md_files:
            # Try .txt file as fallback
            txt_files = [f for f in os.listdir(output_dir) if f.endswith(".txt")]
            if txt_files:
                with open(os.path.join(output_dir, txt_files[0]), "r", encoding="utf-8") as f:
                    return repair_mojibake_text(f.read())
            raise ParseError(
                "No Markdown output found from MinerU",
                file_path=str(path),
                error_type="ocr_failure",
            )

        # Read the first .md file
        md_path = os.path.join(output_dir, md_files[0])
        with open(md_path, "r", encoding="utf-8") as f:
            return repair_mojibake_text(f.read())
