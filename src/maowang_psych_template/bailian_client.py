from __future__ import annotations

import json
import re
from dataclasses import dataclass

import requests
from loguru import logger

from .config import DEFAULT_BAILIAN_ENDPOINT, DEFAULT_BAILIAN_MODEL


class BailianError(RuntimeError):
    pass


@dataclass(slots=True)
class BailianClient:
    api_key: str
    endpoint: str = DEFAULT_BAILIAN_ENDPOINT
    model: str = DEFAULT_BAILIAN_MODEL
    timeout: int = 45

    def validate(self) -> bool:
        if not self.api_key.strip():
            raise BailianError("API Key 为空")
        response_text = self._chat(
            [
                {"role": "system", "content": "You are a strict health-check assistant."},
                {"role": "user", "content": "Reply with exactly OK."},
            ],
            max_tokens=8,
        )
        return "OK" in response_text.upper()

    def choose_image_filename(
        self,
        flow_prompt_en: str,
        filenames: list[str],
        used_filenames: set[str] | None = None,
    ) -> str:
        if not filenames:
            raise BailianError("图片文件名列表为空")

        used_filenames = used_filenames or set()
        prompt = {
            "task": "Choose the best matching image filename for a video storyboard illustration.",
            "rules": [
                "Only use the filenames provided.",
                "Prefer an unused filename when there is a reasonable match.",
                "Do not ask for images. Do not translate. Do not invent a filename.",
                "Return compact JSON only: {\"filename\":\"...\"}",
            ],
            "flow_prompt_en": flow_prompt_en,
            "filenames": filenames,
            "used_filenames": sorted(used_filenames),
        }
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": "You select file names for video templates. Return JSON only.",
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            max_tokens=120,
        )
        filename = _extract_filename(content)
        if filename not in filenames:
            raise BailianError(f"百炼返回了无效文件名: {filename!r}")
        return filename

    def _chat(self, messages: list[dict[str, str]], max_tokens: int) -> str:
        endpoint = _normalize_endpoint(self.endpoint)
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        logger.info("调用百炼 API: model={}, endpoint={}", self.model, endpoint)
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.RequestException as exc:
            raise BailianError(f"百炼 API 请求失败: {exc}") from exc
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise BailianError(f"百炼 API 响应格式异常: {exc}") from exc


def _extract_filename(content: str) -> str:
    text = content.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return str(data.get("filename", "")).strip()
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return str(data.get("filename", "")).strip()
        except json.JSONDecodeError:
            pass
    return text.strip().strip("`'\"")


def _normalize_endpoint(endpoint: str) -> str:
    endpoint = endpoint.strip().rstrip("/")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    return f"{endpoint}/chat/completions"
