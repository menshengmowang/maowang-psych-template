from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger

from .models import StoryboardRow


REQUIRED_COLUMNS = [
    "分镜编号",
    "对应文案",
    "画面内容摘要",
    "Flow提示词英文",
    "Flow提示词中文",
    "参考图建议",
    "失败重试提示词",
    "备注",
]


def _clean_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def read_storyboard_excel(path: Path) -> list[StoryboardRow]:
    logger.info("读取 Excel 分镜: {}", path)
    if not path.exists():
        raise FileNotFoundError(f"Excel 文件不存在: {path}")

    df = pd.read_excel(path, engine="openpyxl")
    df.columns = [str(column).strip() for column in df.columns]

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Excel 缺少字段: {', '.join(missing)}")

    rows: list[StoryboardRow] = []
    for index, row in df.iterrows():
        storyboard = StoryboardRow(
            scene_id=_clean_cell(row["分镜编号"]) or str(index + 1),
            script=_clean_cell(row["对应文案"]),
            summary=_clean_cell(row["画面内容摘要"]),
            flow_prompt_en=_clean_cell(row["Flow提示词英文"]),
            flow_prompt_zh=_clean_cell(row["Flow提示词中文"]),
            reference_suggestion=_clean_cell(row["参考图建议"]),
            retry_prompt=_clean_cell(row["失败重试提示词"]),
            note=_clean_cell(row["备注"]),
            row_number=index + 2,
        )
        if any(
            [
                storyboard.script,
                storyboard.summary,
                storyboard.flow_prompt_en,
                storyboard.flow_prompt_zh,
            ]
        ):
            rows.append(storyboard)

    logger.info("Excel 分镜读取完成: {} 条", len(rows))
    if not rows:
        raise ValueError("Excel 没有可用分镜行")
    return rows

