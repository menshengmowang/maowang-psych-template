from __future__ import annotations

from pathlib import Path

import numpy as np
from loguru import logger
from PIL import Image


def remove_white_background(image_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{image_path.stem}_transparent.png"
    try:
        _remove_background_impl(image_path, output_path)
        logger.info("图片去白底完成: {} -> {}", image_path.name, output_path)
        return output_path
    except Exception as exc:
        logger.exception("图片去白底失败，使用原图: {}", image_path)
        fallback_path = output_dir / image_path.name
        if fallback_path.resolve() != image_path.resolve():
            fallback_path.write_bytes(image_path.read_bytes())
        return fallback_path


def precompose_darken(image_path: Path, output_dir: Path, background_hex: str = "#F4F4F4") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{image_path.stem}_darken.png"
    bg_rgb = _hex_to_rgb(background_hex)
    image = Image.open(image_path).convert("RGBA")
    rgba = np.array(image)
    base_rgb = rgba[:, :, :3]
    darkened = np.minimum(base_rgb, np.array(bg_rgb, dtype=np.uint8).reshape(1, 1, 3))
    output_rgba = rgba.copy()
    output_rgba[:, :, :3] = darkened
    Image.fromarray(output_rgba, mode="RGBA").save(output_path)
    logger.info("预合成变暗完成: {} -> {}", image_path, output_path)
    return output_path


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"无效颜色值: {hex_color}")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _remove_background_impl(image_path: Path, output_path: Path) -> None:
    import cv2
    image = Image.open(image_path).convert("RGBA")
    rgba = np.array(image)
    rgb = rgba[:, :, :3].astype(np.float32)
    original_alpha = rgba[:, :, 3].astype(np.float32)
    height, width = rgb.shape[:2]
    if height < 4 or width < 4:
        image.save(output_path)
        return

    strip = max(2, min(width, height) // 40)
    corner = max(4, min(width, height) // 12)

    edge_samples = np.concatenate(
        [
            rgb[:strip, :, :].reshape(-1, 3),
            rgb[-strip:, :, :].reshape(-1, 3),
            rgb[:, :strip, :].reshape(-1, 3),
            rgb[:, -strip:, :].reshape(-1, 3),
            rgb[:corner, :corner, :].reshape(-1, 3),
            rgb[:corner, -corner:, :].reshape(-1, 3),
            rgb[-corner:, :corner, :].reshape(-1, 3),
            rgb[-corner:, -corner:, :].reshape(-1, 3),
        ],
        axis=0,
    )
    bg_color = np.median(edge_samples, axis=0)
    distances = np.linalg.norm(rgb - bg_color, axis=2)
    edge_distances = np.linalg.norm(edge_samples - bg_color, axis=1)
    threshold = float(np.clip(np.percentile(edge_distances, 92) + 22, 26, 86))

    close_to_bg = (distances <= threshold).astype(np.uint8)
    connected = _edge_connected_mask(close_to_bg)

    alpha = np.full((height, width), 255, dtype=np.float32)
    alpha[connected > 0] = 0
    feather = max(3, min(width, height) // 260)
    if feather % 2 == 0:
        feather += 1
    alpha = cv2.GaussianBlur(alpha, (feather, feather), 0)
    alpha = np.minimum(alpha, original_alpha)

    output = rgba.copy()
    output[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    Image.fromarray(output, mode="RGBA").save(output_path)


def _edge_connected_mask(mask: np.ndarray) -> np.ndarray:
    import cv2
    label_count, labels = cv2.connectedComponents(mask, connectivity=8)
    if label_count <= 1:
        return np.zeros_like(mask, dtype=np.uint8)

    border_labels = set(np.unique(labels[0, :]).tolist())
    border_labels.update(np.unique(labels[-1, :]).tolist())
    border_labels.update(np.unique(labels[:, 0]).tolist())
    border_labels.update(np.unique(labels[:, -1]).tolist())
    border_labels.discard(0)
    if not border_labels:
        return np.zeros_like(mask, dtype=np.uint8)
    return np.isin(labels, list(border_labels)).astype(np.uint8)
