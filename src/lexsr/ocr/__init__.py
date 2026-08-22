"""
OCR pipeline for scanned legal documents.

Multi-engine approach:
1. Digital PDFs: PyPDF2 text extraction (fast, accurate)
2. Scanned PDFs: Tesseract OCR (free, good quality)
3. High-quality scans: Optional Qwen2.5-VL/EasyOCR (best quality)

Features:
- Automatic detection of digital vs scanned
- Confidence scoring
- Layout preservation
- Structure detection (articles, paragraphs)
- Multi-language support (Dutch, English)
- Bronze layer integration
"""

from .extractor import PDFExtractor, OCREngine, OCRResult
from .detector import StructureDetector, DetectedArticle, DetectedStructure
from .pipeline import OCRPipeline, PipelineConfig, PipelineResult

__all__ = [
    "PDFExtractor",
    "OCREngine",
    "OCRResult",
    "StructureDetector",
    "DetectedArticle",
    "DetectedStructure",
    "OCRPipeline",
    "PipelineConfig",
    "PipelineResult",
]
