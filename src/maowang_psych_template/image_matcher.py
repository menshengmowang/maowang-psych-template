from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from loguru import logger

from .bailian_client import BailianClient, BailianError
from .models import SceneMatch


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


class MatchCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, str] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.data = {}
            return
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("读取 match_cache.json 失败，将重建缓存: {}", exc)
            self.data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def key(self, prompt: str, filenames: list[str], model: str) -> str:
        payload = json.dumps(
            {"prompt": prompt, "filenames": sorted(filenames), "model": model},
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        self.data[key] = value


def list_image_filenames(image_dir: Path) -> list[str]:
    if not image_dir.exists():
        raise FileNotFoundError(f"图片文件夹不存在: {image_dir}")
    filenames = sorted(
        item.name
        for item in image_dir.iterdir()
        if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not filenames:
        raise ValueError(f"图片文件夹没有可用图片: {image_dir}")
    logger.info("读取图片文件名: {} 个", len(filenames))
    return filenames


def match_images_for_scenes(
    scenes: list[SceneMatch],
    image_dir: Path,
    client: BailianClient | None,
    cache: MatchCache,
) -> list[SceneMatch]:
    filenames = list_image_filenames(image_dir)
    used: set[str] = set()

    for scene in scenes:
        prompt = scene.storyboard.flow_prompt_en or scene.storyboard.summary or scene.storyboard.script
        cache_key = cache.key(prompt, filenames, client.model if client else "local-fallback")
        selected = cache.get(cache_key)
        if selected not in filenames:
            selected = None

        if selected:
            logger.info("图片匹配缓存命中: 分镜 {} -> {}", scene.storyboard.scene_id, selected)
        elif client and client.api_key.strip():
            try:
                selected = client.choose_image_filename(prompt, filenames, used)
                logger.info("百炼图片匹配: 分镜 {} -> {}", scene.storyboard.scene_id, selected)
            except BailianError as exc:
                logger.error("百炼图片匹配失败，使用本地兜底: {}", exc)
                scene.warnings.append(str(exc))
                selected = _local_fallback_match(prompt, filenames, used)
        else:
            logger.warning("未配置百炼 API Key，使用本地文件名兜底匹配")
            scene.warnings.append("未配置百炼 API Key，使用本地文件名兜底匹配")
            selected = _local_fallback_match(prompt, filenames, used)

        if selected in used and len(used) < len(filenames):
            selected = _local_fallback_match(prompt, filenames, used)
        scene.selected_image = selected
        used.add(selected)
        cache.set(cache_key, selected)

    cache.save()
    return scenes


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", value.lower())
        if len(token) >= 2
    }


def _local_fallback_match(prompt: str, filenames: list[str], used: set[str]) -> str:
    prompt_tokens = _tokens(prompt)
    candidates = [name for name in filenames if name not in used] or filenames
    best_name = candidates[0]
    best_score = -1
    for name in candidates:
        name_tokens = _tokens(Path(name).stem)
        score = len(prompt_tokens & name_tokens)
        if score > best_score:
            best_score = score
            best_name = name
    return best_name

