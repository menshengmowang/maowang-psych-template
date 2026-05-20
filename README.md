# 魔王心理学模板

这是一个 Windows 桌面软件项目，用于根据 Excel 分镜、SRT 中文字幕、配音和图片素材，直接生成剪映专业版 Windows 中文版能够识别的草稿目录。

草稿写入器迁移自已有可用项目 `jianying-auto-draft`：使用 `pyJianYingDraft` 的 `DraftFolder.create_draft()` / `ScriptFile.save()` 路径生成 `draft_content.json` 和 `draft_meta_info.json`，不再依赖模板草稿或 sidecar manifest。

## 功能

- 读取 Excel 分镜字段。
- 解析 SRT 中文字幕。
- 按顺序匹配 Excel「对应文案」和 SRT 字幕时间段。
- 使用阿里云百炼 OpenAI 兼容接口，仅根据英文提示词和图片文件名列表选择最匹配图片。
- 使用 `match_cache.json` 缓存图片匹配结果。
- 对插图自动去白底，输出透明 PNG。
- 生成 6px / 8px / 10px 黑色分割线，或复制自定义线条图片。
- 复制音频、Logo、背景图、处理后的插图到剪映草稿资产目录。
- 生成剪映可识别的 `draft_content.json` 和 `draft_meta_info.json`。
- 输出 `logs/app.log` 和 `logs/error.log`。
- 提供 PySide6 GUI 和 PyInstaller 打包脚本。

## 安装运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m maowang_psych_template
```

如果直接从源码运行，请确保当前目录包含 `src`，或使用：

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m maowang_psych_template
```

## 打包

```powershell
.\scripts\build.ps1
```

生成物位于 `dist\魔王心理学模板`。

## 百炼 API

默认使用阿里云百炼 / DashScope 的 OpenAI 兼容 Chat Completions 接口：

`https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`

参考阿里云官方文档：[OpenAI 接口兼容说明](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)。

GUI 中可以修改 endpoint 和 model。API Key 会保存到当前 Windows 用户的 `%APPDATA%\MaowangPsychTemplate\config.json`。

## 剪映草稿说明

输出目录会直接写入用户选择的剪映草稿根目录，目录内包括：

- `draft_content.json`：由 `pyJianYingDraft` 生成的剪映时间线内容。
- `draft_meta_info.json`：由 `pyJianYingDraft` 生成并补充草稿名称、路径和修改时间字段。
- `maowang_assets/`：复制或生成后的素材，供剪映草稿引用。

打开剪映专业版首页后应能看到新草稿；如果草稿列表未刷新，可以重启剪映专业版。
