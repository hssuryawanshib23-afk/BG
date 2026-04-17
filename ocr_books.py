from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR


PROJECT_DIRECTORY = Path(__file__).resolve().parent
BOOKS_DIRECTORY = PROJECT_DIRECTORY / "Books"
OCR_OUTPUT_DIRECTORY = PROJECT_DIRECTORY / "OCR_Output"
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED_PDF_SUFFIXES = {".pdf"}
TEXT_MASK_PADDING_PIXELS = 12
FIGURE_PADDING_PIXELS = 14


class OcrPipelineError(RuntimeError):
    pass


@dataclass(slots=True)
class TextBlock:
    bounding_box: list[list[float]]
    text: str
    confidence: float


@dataclass(slots=True)
class FigureRegion:
    page_number: int
    bounding_box: list[int]
    figure_name: str
    caption_text: str | None
    image_path: str
    width: int
    height: int
    text_density: float
    non_text_density: float
    review_status: str
    review_notes: str


def ensure_directory_exists(directory_path: Path) -> None:
    directory_path.mkdir(parents=True, exist_ok=True)


def recreate_directory(directory_path: Path) -> None:
    if directory_path.exists():
        shutil.rmtree(directory_path)
    directory_path.mkdir(parents=True, exist_ok=True)


def sanitize_file_name(file_name: str) -> str:
    sanitized_text = re.sub(r"[^A-Za-z0-9._-]+", "-", file_name.strip())
    sanitized_text = re.sub(r"-{2,}", "-", sanitized_text).strip("-")
    return sanitized_text or "unnamed"


def list_supported_book_files(books_directory: Path) -> list[Path]:
    if not books_directory.exists():
        raise OcrPipelineError(f"Books directory does not exist: {books_directory}")

    book_files = []
    for file_path in sorted(books_directory.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() in SUPPORTED_PDF_SUFFIXES | SUPPORTED_IMAGE_SUFFIXES:
            book_files.append(file_path)
    return book_files


def build_output_directory_for_book(book_file_path: Path) -> Path:
    return OCR_OUTPUT_DIRECTORY / book_file_path.stem


def convert_pdf_to_page_images(book_file_path: Path, page_images_directory: Path) -> list[Path]:
    ensure_directory_exists(page_images_directory)
    output_prefix = page_images_directory / "page"
    command = ["pdftoppm", "-png", str(book_file_path), str(output_prefix)]
    completed_process = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed_process.returncode != 0:
        raise OcrPipelineError(completed_process.stderr.strip() or f"Failed to convert PDF: {book_file_path}")

    page_image_paths = sorted(page_images_directory.glob("page-*.png"))
    if not page_image_paths:
        raise OcrPipelineError(f"No page images were created for: {book_file_path}")
    return page_image_paths


def copy_image_as_single_page(book_file_path: Path, page_images_directory: Path) -> list[Path]:
    ensure_directory_exists(page_images_directory)
    page_image_path = page_images_directory / f"page-01{book_file_path.suffix.lower()}"
    page_image_path.write_bytes(book_file_path.read_bytes())
    return [page_image_path]


def preprocess_image(source_image_path: Path, destination_image_path: Path) -> None:
    source_image = cv2.imread(str(source_image_path))
    if source_image is None:
        raise OcrPipelineError(f"Could not read image: {source_image_path}")

    grayscale_image = cv2.cvtColor(source_image, cv2.COLOR_BGR2GRAY)
    denoised_image = cv2.GaussianBlur(grayscale_image, (3, 3), 0)
    _, threshold_image = cv2.threshold(
        denoised_image,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )

    if not cv2.imwrite(str(destination_image_path), threshold_image):
        raise OcrPipelineError(f"Could not write image: {destination_image_path}")


def extract_text_blocks(image_path: Path, ocr_engine: RapidOCR) -> list[TextBlock]:
    raw_result, _ = ocr_engine(str(image_path))
    if not raw_result:
        return []

    text_blocks: list[TextBlock] = []
    for bounding_box, text, confidence in raw_result:
        cleaned_text = text.strip()
        if not cleaned_text:
            continue
        text_blocks.append(
            TextBlock(
                bounding_box=bounding_box,
                text=cleaned_text,
                confidence=float(confidence),
            )
        )
    return text_blocks


def build_page_text(text_blocks: list[TextBlock]) -> str:
    return "\n".join(text_block.text for text_block in text_blocks)


def build_bounding_rectangle(bounding_box: list[list[float]]) -> tuple[int, int, int, int]:
    x_coordinates = [int(point[0]) for point in bounding_box]
    y_coordinates = [int(point[1]) for point in bounding_box]
    left = min(x_coordinates)
    top = min(y_coordinates)
    right = max(x_coordinates)
    bottom = max(y_coordinates)
    return left, top, right, bottom


def build_text_mask(image_shape: tuple[int, int], text_blocks: list[TextBlock]) -> cv2.typing.MatLike:
    image_height, image_width = image_shape
    text_mask = np.zeros((image_height, image_width), dtype=np.uint8)

    for text_block in text_blocks:
        left, top, right, bottom = build_bounding_rectangle(text_block.bounding_box)
        padded_left = max(0, left - TEXT_MASK_PADDING_PIXELS)
        padded_top = max(0, top - TEXT_MASK_PADDING_PIXELS)
        padded_right = min(image_width - 1, right + TEXT_MASK_PADDING_PIXELS)
        padded_bottom = min(image_height - 1, bottom + TEXT_MASK_PADDING_PIXELS)
        cv2.rectangle(
            text_mask,
            (padded_left, padded_top),
            (padded_right, padded_bottom),
            color=255,
            thickness=-1,
        )

    return text_mask


def build_content_mask(grayscale_image: cv2.typing.MatLike) -> cv2.typing.MatLike:
    _, threshold_image = cv2.threshold(
        grayscale_image,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    return threshold_image


def find_caption_text_for_region(
    region_left: int,
    region_top: int,
    region_right: int,
    region_bottom: int,
    text_blocks: list[TextBlock],
) -> tuple[str, str | None]:
    figure_pattern = re.compile(r"\bfig(?:ure)?\.?\s*\d+(?:\.\d+)?[A-Za-z]?\b", re.IGNORECASE)
    closest_match_distance: int | None = None
    closest_match_text: str | None = None
    closest_match_name: str | None = None

    for text_block in text_blocks:
        match = figure_pattern.search(text_block.text)
        if not match:
            continue

        left, top, right, bottom = build_bounding_rectangle(text_block.bounding_box)
        has_horizontal_overlap = not (right < region_left or left > region_right)
        vertical_distance = min(abs(top - region_bottom), abs(bottom - region_top))

        if not has_horizontal_overlap and vertical_distance > 140:
            continue
        if closest_match_distance is not None and vertical_distance >= closest_match_distance:
            continue

        closest_match_distance = vertical_distance
        closest_match_text = text_block.text
        closest_match_name = sanitize_file_name(match.group(0).replace(" ", ""))

    if closest_match_name is not None:
        return closest_match_name, closest_match_text

    fallback_name = f"page-{region_top}-figure-{region_left}"
    return sanitize_file_name(fallback_name), None


def detect_figure_regions(
    page_number: int,
    page_image_path: Path,
    text_blocks: list[TextBlock],
    figures_directory: Path,
) -> list[FigureRegion]:
    source_image = cv2.imread(str(page_image_path))
    if source_image is None:
        raise OcrPipelineError(f"Could not read page image for figure extraction: {page_image_path}")

    image_height, image_width = source_image.shape[:2]
    grayscale_image = cv2.cvtColor(source_image, cv2.COLOR_BGR2GRAY)
    content_mask = build_content_mask(grayscale_image)
    text_mask = build_text_mask((image_height, image_width), text_blocks)

    non_text_mask = cv2.bitwise_and(content_mask, cv2.bitwise_not(text_mask))
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    dilated_mask = cv2.morphologyEx(non_text_mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)

    contours, _ = cv2.findContours(dilated_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detected_regions: list[FigureRegion] = []
    used_file_names: set[str] = set()

    minimum_area = image_height * image_width * 0.01
    minimum_width = int(image_width * 0.12)
    minimum_height = int(image_height * 0.08)

    for contour in contours:
        left, top, width, height = cv2.boundingRect(contour)
        area = width * height
        if area < minimum_area:
            continue
        if width < minimum_width or height < minimum_height:
            continue
        if top < int(image_height * 0.05) and height < int(image_height * 0.15):
            continue

        region_left = max(0, left - FIGURE_PADDING_PIXELS)
        region_top = max(0, top - FIGURE_PADDING_PIXELS)
        region_right = min(image_width, left + width + FIGURE_PADDING_PIXELS)
        region_bottom = min(image_height, top + height + FIGURE_PADDING_PIXELS)

        region_area = max(1, (region_right - region_left) * (region_bottom - region_top))
        region_text_mask = text_mask[region_top:region_bottom, region_left:region_right]
        region_non_text_mask = non_text_mask[region_top:region_bottom, region_left:region_right]
        text_density = cv2.countNonZero(region_text_mask) / region_area
        non_text_density = cv2.countNonZero(region_non_text_mask) / region_area
        aspect_ratio = (region_right - region_left) / max(1, region_bottom - region_top)

        if non_text_density < 0.015:
            continue
        if text_density > 0.22 and non_text_density < 0.09:
            continue
        if aspect_ratio > 4.5 and text_density > 0.10:
            continue
        if (region_bottom - region_top) < int(image_height * 0.10) and text_density > 0.08:
            continue

        figure_name, caption_text = find_caption_text_for_region(
            region_left=region_left,
            region_top=region_top,
            region_right=region_right,
            region_bottom=region_bottom,
            text_blocks=text_blocks,
        )

        if caption_text is None and text_density > 0.18:
            continue

        file_stem = sanitize_file_name(f"page-{page_number:02d}-{figure_name}")
        unique_file_stem = file_stem
        duplicate_index = 2
        while unique_file_stem in used_file_names:
            unique_file_stem = f"{file_stem}-{duplicate_index}"
            duplicate_index += 1
        used_file_names.add(unique_file_stem)

        figure_image_path = figures_directory / f"{unique_file_stem}.png"
        figure_crop = source_image[region_top:region_bottom, region_left:region_right]
        if figure_crop.size == 0:
            continue
        cv2.imwrite(str(figure_image_path), figure_crop)

        detected_regions.append(
            FigureRegion(
                page_number=page_number,
                bounding_box=[region_left, region_top, region_right, region_bottom],
                figure_name=unique_file_stem,
                caption_text=caption_text,
                image_path=str(figure_image_path),
                width=region_right - region_left,
                height=region_bottom - region_top,
                text_density=round(text_density, 4),
                non_text_density=round(non_text_density, 4),
                review_status="pending",
                review_notes="",
            )
        )

    detected_regions.sort(key=lambda region: (region.page_number, region.bounding_box[1], region.bounding_box[0]))
    return detected_regions


def write_page_output(
    page_number: int,
    page_image_path: Path,
    preprocessed_image_path: Path,
    page_text_directory: Path,
    figures_directory: Path,
    ocr_engine: RapidOCR,
) -> dict[str, object]:
    text_blocks = extract_text_blocks(preprocessed_image_path, ocr_engine)
    page_text = build_page_text(text_blocks)
    figure_regions = detect_figure_regions(
        page_number=page_number,
        page_image_path=page_image_path,
        text_blocks=text_blocks,
        figures_directory=figures_directory,
    )

    text_path = page_text_directory / f"page-{page_number:02d}.txt"
    blocks_path = page_text_directory / f"page-{page_number:02d}.blocks.json"

    text_path.write_text(page_text, encoding="utf-8")
    blocks_path.write_text(
        json.dumps([asdict(text_block) for text_block in text_blocks], indent=2),
        encoding="utf-8",
    )

    return {
        "page_number": page_number,
        "text_path": str(text_path),
        "blocks_path": str(blocks_path),
        "block_count": len(text_blocks),
        "character_count": len(page_text),
        "figure_count": len(figure_regions),
        "figures": [asdict(figure_region) for figure_region in figure_regions],
    }


def write_figure_review_manifest(output_directory: Path, pages: list[dict[str, object]]) -> Path:
    review_manifest_path = output_directory / "figure_review_manifest.json"
    review_items = []

    for page in pages:
        figures = page["figures"]
        if not isinstance(figures, list):
            continue
        for figure in figures:
            review_items.append(
                {
                    "figure_name": figure["figure_name"],
                    "page_number": figure["page_number"],
                    "image_path": figure["image_path"],
                    "caption_text": figure["caption_text"],
                    "bounding_box": figure["bounding_box"],
                    "text_density": figure["text_density"],
                    "non_text_density": figure["non_text_density"],
                    "review_status": figure["review_status"],
                    "review_notes": figure["review_notes"],
                }
            )

    review_manifest_path.write_text(json.dumps(review_items, indent=2), encoding="utf-8")
    return review_manifest_path


def process_book_file(book_file_path: Path, ocr_engine: RapidOCR) -> Path:
    output_directory = build_output_directory_for_book(book_file_path)
    page_images_directory = output_directory / "page_images"
    preprocessed_images_directory = output_directory / "preprocessed_page_images"
    page_text_directory = output_directory / "page_text"
    figures_directory = output_directory / "figures"

    recreate_directory(output_directory)
    ensure_directory_exists(preprocessed_images_directory)
    ensure_directory_exists(page_text_directory)
    ensure_directory_exists(figures_directory)

    if book_file_path.suffix.lower() in SUPPORTED_PDF_SUFFIXES:
        page_image_paths = convert_pdf_to_page_images(book_file_path, page_images_directory)
    else:
        page_image_paths = copy_image_as_single_page(book_file_path, page_images_directory)

    pages = []
    for page_number, page_image_path in enumerate(page_image_paths, start=1):
        preprocessed_image_path = preprocessed_images_directory / f"page-{page_number:02d}.png"
        preprocess_image(page_image_path, preprocessed_image_path)
        page_data = write_page_output(
            page_number=page_number,
            page_image_path=page_image_path,
            preprocessed_image_path=preprocessed_image_path,
            page_text_directory=page_text_directory,
            figures_directory=figures_directory,
            ocr_engine=ocr_engine,
        )
        page_data["page_image_path"] = str(page_image_path)
        page_data["preprocessed_image_path"] = str(preprocessed_image_path)
        pages.append(page_data)

    review_manifest_path = write_figure_review_manifest(output_directory, pages)
    manifest_path = output_directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_file_path": str(book_file_path),
                "generated_at": datetime.now(UTC).isoformat(),
                "page_count": len(pages),
                "figure_count": sum(int(page["figure_count"]) for page in pages),
                "figure_review_manifest_path": str(review_manifest_path),
                "pages": pages,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def run_ocr_pipeline() -> list[Path]:
    book_files = list_supported_book_files(BOOKS_DIRECTORY)
    ensure_directory_exists(OCR_OUTPUT_DIRECTORY)

    ocr_engine = RapidOCR()
    manifest_paths = []
    for book_file_path in book_files:
        manifest_paths.append(process_book_file(book_file_path, ocr_engine))
    return manifest_paths


def main() -> None:
    manifest_paths = run_ocr_pipeline()
    for manifest_path in manifest_paths:
        print(manifest_path)


if __name__ == "__main__":
    main()
