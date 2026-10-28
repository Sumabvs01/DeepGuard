from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps
from transformers import pipeline

MODEL_NAME = "Wvolf/ViT_Deepfake_Detection"


@lru_cache(maxsize=1)
def get_model():
    return pipeline(
        "image-classification",
        model=MODEL_NAME,
        device=-1,
    )


def predict_image(image_path):
    path = Path(image_path)

    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")

    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")

    predictions = get_model()(image, top_k=None)

    scores = {
        item["label"].strip().lower(): float(item["score"])
        for item in predictions
    }

    real_score = scores.get("real")
    fake_score = scores.get("fake")

    if real_score is None or fake_score is None:
        raise RuntimeError(
            "Model did not return recognizable Real/Fake labels. "
            f"Labels received: {list(scores.keys())}"
        )

    return {
        "prediction": "FAKE" if fake_score > real_score else "REAL",
        "confidence": round(max(real_score, fake_score) * 100, 2),
        "real_score": round(real_score * 100, 2),
        "fake_score": round(fake_score * 100, 2),
        "model": MODEL_NAME,
        "warning": "Experimental AI prediction, not proof of authenticity.",
    }


def predict_video(frame_paths):
    results = []

    for frame_path in frame_paths:
        try:
            results.append(predict_image(frame_path))
        except Exception as exc:
            print(f"Frame analysis failed: {exc}")

    if not results:
        return {
            "prediction": "INCONCLUSIVE",
            "confidence": None,
            "frames_analyzed": 0,
        }

    real_score = sum(r["real_score"] for r in results) / len(results)
    fake_score = sum(r["fake_score"] for r in results) / len(results)

    return {
        "prediction": "FAKE" if fake_score > real_score else "REAL",
        "confidence": round(max(real_score, fake_score), 2),
        "real_score": round(real_score, 2),
        "fake_score": round(fake_score, 2),
        "frames_analyzed": len(results),
        "warning": "Frame-based estimate; not proof of authenticity.",
    }
