"""A local calorie log; numbers are user-entered or clearly marked estimates."""
import json
from pathlib import Path
import mimetypes
from core import food_log, outcome

PLUGIN = {"name": "food_tracker",
    "description": "Add a food item with calories, list a day's log and total, or remove one by ID. Calorie values are user supplied or estimates, not medical advice. The diary stays local.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["add", "list", "remove", "adjust", "estimate_photo"]},
        "food": {"type": "STRING"}, "kcal": {"type": "INTEGER"},
        "estimate": {"type": "BOOLEAN"}, "day": {"type": "STRING"},
        "item_id": {"type": "STRING"}, "image_path": {"type": "STRING"}}, "required": ["action"]}}


def run(parameters, player=None, session_memory=None):
    try:
        p = parameters or {}; action = p.get("action")
        if action == "add":
            row = food_log.add(p.get("food", ""), p.get("kcal", -1), p.get("estimate", False), p.get("day"))
            return outcome.done("food_added", data=json.dumps(row, ensure_ascii=False), note="Nutrition estimate, not medical advice")
        if action == "list":
            data = food_log.list_day(p.get("day"))
            if player: player.show_content("Diário alimentar", json.dumps(data, ensure_ascii=False, indent=2))
            return outcome.done("food_log", data=json.dumps(data, ensure_ascii=False))
        if action == "remove":
            row = food_log.remove(p.get("item_id", ""))
            return outcome.done("food_removed", data=json.dumps(row, ensure_ascii=False))
        if action == "adjust":
            row = food_log.adjust(p.get("item_id", ""), p.get("kcal", -1))
            return outcome.done("food_adjusted", data=json.dumps(row, ensure_ascii=False), note="Adjusted value is marked as an estimate")
        if action == "estimate_photo":
            path = Path(str(p.get("image_path", ""))).expanduser().resolve(strict=True)
            if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp") or path.stat().st_size > 8_000_000:
                raise ValueError("Use a JPG, PNG or WebP image up to 8 MB")
            mime = mimetypes.guess_type(path.name)[0]
            if mime not in ("image/jpeg", "image/png", "image/webp"):
                raise ValueError("Unsupported image format")
            from google.genai import types
            from core import gemini
            part = types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)
            response = gemini.call([part, "Estimate the calories visible in this meal image. Return a concise range, name the food assumptions, and clearly state uncertainty. Do not present this as medical advice. Do not infer a person's health."], tier=gemini.SMART, timeout_ms=60000)
            text = str(getattr(response, "text", "") or "").strip()
            if not text: raise RuntimeError("No estimate returned")
            if player: player.show_content("Estimativa por imagem — confirmar", text[:3000] + "\n\nNada foi adicionado ao diário. Confirme a porção e adicione manualmente se desejar.")
            return outcome.unverified("food_photo_estimate", "Visual estimate only; confirm portion and calories before logging", estimate=text[:1200])
        return outcome.failed("food_log", "Unknown action")
    except Exception as exc:
        return outcome.failed("food_log", str(exc)[:240])
