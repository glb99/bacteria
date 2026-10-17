"""One-off: ask a visual model for diagram boxes on image.png."""

from google.genai import types
from google import genai
import json
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
load_dotenv(HERE.parents[3] / ".env")


MODEL_ID = "gemini-3.5-flash"


class Box(BaseModel):
    """One diagram box. Edges are 0-1000 relative to the image."""

    label: str
    ymin: int = Field(
        description="Top edge, 0 at the top of the image, 1000 at the bottom.")
    xmin: int = Field(
        description="Left edge, 0 at the left, 1000 at the right.")
    ymax: int
    xmax: int


class Detections(BaseModel):
    boxes: list[Box]


def load_image_as_bytes(path: Path) -> bytes:
    return path.read_bytes()


def draw_boxes(image_path: Path, boxes: list[Box], output_path: Path) -> None:
    """Draw each 0-1000 box onto a copy of the page."""
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for box in boxes:
        left = box.xmin / 1000 * width
        top = box.ymin / 1000 * height
        right = box.xmax / 1000 * width
        bottom = box.ymax / 1000 * height
        draw.rectangle((left, top, right, bottom), outline="red", width=3)
        draw.text((left, max(0, top - 14)), box.label, fill="red")
    image.save(output_path)


def main() -> None:
    page_image_bytes = load_image_as_bytes(HERE / "image.png")
    prompt = (
        "Detect each diagram on this page as one 2d bounding box. "
        "A diagram is the whole figure. "
        "Do not box the shapes, arrows, or labels inside it."
        "Also detect text blocks, tables, and charts as separate boxes. "
    )
    client = genai.Client()
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=[
            types.Part.from_bytes(data=page_image_bytes,
                                  mime_type="image/png"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Detections,
        ),
    )
    detections = Detections.model_validate_json(response.text or "")
    print(json.dumps(detections.model_dump(), indent=2))
    output_path = HERE / "image.boxes.png"
    draw_boxes(HERE / "image.png", detections.boxes, output_path)
    print(output_path)


if __name__ == "__main__":
    main()
