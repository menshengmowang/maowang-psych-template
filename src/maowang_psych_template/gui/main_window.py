from __future__ import annotations

from pathlib import Path
import difflib
from typing import Any

from loguru import logger
from PySide6.QtCore import QObject, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..bailian_client import BailianClient
from ..config import AppConfig, load_config, save_config
from ..logging_config import log_dir, setup_logging
from ..models import GenerationInputs
from ..models import (
    ILLUSTRATION_MODE_DARKEN,
    ILLUSTRATION_MODE_ORIGINAL,
    ILLUSTRATION_MODE_PRECOMPOSE_DARKEN,
    ILLUSTRATION_MODE_REMOVE_WHITE,
)
from ..pipeline import GenerationPipeline


POSITION_TARGETS: dict[str, tuple[str, str, str, int, int]] = {
    "logo": ("Logo", "logo_x_spin", "logo_y_spin", 70, 45),
    "title": ("标题文字", "title_x_spin", "title_y_spin", 320, 60),
    "hint": ("顶部右侧提示文字", "hint_x_spin", "hint_y_spin", 1250, 65),
    "illustration": ("插图", "illustration_center_x_spin", "illustration_center_y_spin", 960, 440),
    "divider": ("黑色分割线", "divider_center_x_spin", "divider_center_y_spin", 960, 810),
    "subtitle": ("字幕", "subtitle_center_x_spin", "subtitle_center_y_spin", 960, 940),
}


class GenerationWorker(QObject):
    progress = Signal(str)
    finished = Signal(str, str, str)
    failed = Signal(str)

    def __init__(self, config: AppConfig, inputs: GenerationInputs, mode: str) -> None:
        super().__init__()
        self.config = config
        self.inputs = inputs
        self.mode = mode

    def run(self) -> None:
        try:
            setup_logging()
            pipeline = GenerationPipeline(self.config, self.progress.emit)
            if self.mode == "check":
                result = pipeline.check_matches(self.inputs)
                self.finished.emit("check", str(result.report_path), str(result.report_path))
            else:
                result = pipeline.run(self.inputs)
                report_path = str(result.match_report_path) if result.match_report_path else ""
                self.finished.emit("generate", str(result.output_dir), report_path)
        except Exception as exc:
            logger.exception("生成任务失败")
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("魔王心理学模板")
        self.config = load_config()
        self.worker_thread: QThread | None = None
        self.worker: GenerationWorker | None = None
        self.last_report_path: Path | None = None
        self.last_draft_dir: Path | None = None
        self.action_buttons: list[QPushButton] = []
        self.position_labels: dict[str, QLabel] = {}
        self.position_step_combos: dict[str, QComboBox] = {}
        self._build_ui()
        self._load_config_to_ui()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)

        title = QLabel("魔王心理学模板")
        title.setStyleSheet("font-size: 26px; font-weight: 700;")
        root.addWidget(title)
        subtitle = QLabel("心理学模板剪映草稿生成器")
        subtitle.setStyleSheet("font-size: 14px; color: #666;")
        root.addWidget(subtitle)

        self._init_position_spins()

        tabs = QTabWidget()
        tabs.addTab(self._scroll_page(self._build_input_group()), "基础输入")
        tabs.addTab(self._scroll_page(self._build_api_group()), "AI 匹配")
        tabs.addTab(self._scroll_page(self._build_layout_tab()), "画面样式")
        tabs.addTab(self._scroll_page(self._build_font_style_tab()), "字体样式")
        tabs.addTab(self._scroll_page(self._build_advanced_tab()), "高级设置")
        tabs.addTab(self._build_run_log_tab(), "生成草稿")
        tabs.addTab(self._build_log_tab(), "日志")
        root.addWidget(tabs, 1)

        self.setCentralWidget(central)

    def _scroll_page(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def _build_input_group(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        group = QGroupBox("核心输入")
        grid = QGridLayout(group)

        self.excel_edit = self._path_row(grid, 0, "Excel 分镜文件", "file", "Excel 文件 (*.xlsx *.xls)")
        self.srt_edit = self._path_row(grid, 1, "SRT 中文字幕文件", "file", "SRT 字幕 (*.srt)")
        self.audio_edit = self._path_row(grid, 2, "配音文件", "file", "音频文件 (*.mp3 *.wav *.m4a *.aac *.flac)")
        self.image_dir_edit = self._path_row(grid, 3, "图片文件夹", "dir", "")
        self.logo_edit = self._path_row(grid, 4, "Logo 图片", "file", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        self.background_edit = self._path_row(grid, 5, "背景图（可选）", "file", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        self.divider_edit = self._path_row(grid, 6, "黑色分割线图片", "file", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        self.draft_dir_edit = self._path_row(grid, 7, "剪映草稿目录", "dir", "")
        self.output_name_edit = QLineEdit()
        grid.addWidget(QLabel("输出草稿名（可选）"), 8, 0)
        grid.addWidget(self.output_name_edit, 8, 1)

        root.addWidget(group)
        root.addStretch(1)
        return page

    def _build_api_group(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        group = QGroupBox("阿里云百炼 API")
        form = QFormLayout(group)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.endpoint_edit = QLineEdit()
        self.model_edit = QLineEdit()

        button_row = QHBoxLayout()
        self.validate_button = QPushButton("验证")
        self.validate_button.clicked.connect(self._validate_api)
        self.save_button = QPushButton("保存配置")
        self.save_button.clicked.connect(self._save_config_from_ui)
        button_row.addWidget(self.validate_button)
        button_row.addWidget(self.save_button)
        button_row.addStretch(1)

        form.addRow("API Key", self.api_key_edit)
        form.addRow("Endpoint", self.endpoint_edit)
        form.addRow("Model", self.model_edit)
        form.addRow("", button_row)

        root.addWidget(group)
        root.addStretch(1)
        return page

    def _build_layout_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)

        style_group = QGroupBox("基础版式参数")
        form = QFormLayout(style_group)
        self.title_text_edit = QLineEdit()
        self.hint_text_edit = QLineEdit()
        self.illustration_max_width_spin = self._spin_box(100, 1600)
        self.illustration_max_height_spin = self._spin_box(100, 900)
        self.logo_max_size_spin = self._spin_box(20, 300)
        self.illustration_fusion_combo = QComboBox()
        self.illustration_fusion_combo.addItem("软件预合成变暗效果（推荐）", ILLUSTRATION_MODE_PRECOMPOSE_DARKEN)
        self.illustration_fusion_combo.addItem("原图 + 剪映变暗混合模式（实验）", ILLUSTRATION_MODE_DARKEN)
        self.illustration_fusion_combo.addItem("自动去白底 PNG", ILLUSTRATION_MODE_REMOVE_WHITE)
        self.illustration_fusion_combo.addItem("原图不处理", ILLUSTRATION_MODE_ORIGINAL)
        form.addRow("顶部标题", self.title_text_edit)
        form.addRow("顶部右侧提示文字", self.hint_text_edit)
        form.addRow("Logo 最大尺寸", self.logo_max_size_spin)
        form.addRow("插图最大宽度", self.illustration_max_width_spin)
        form.addRow("插图最大高度", self.illustration_max_height_spin)
        form.addRow("插图融合方式", self.illustration_fusion_combo)
        root.addWidget(style_group)

        position_group = QGroupBox("位置微调")
        position_root = QVBoxLayout(position_group)
        for key in POSITION_TARGETS:
            position_root.addWidget(self._build_position_control(key))
        root.addWidget(position_group)
        root.addStretch(1)
        return page

    def _build_font_style_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.addWidget(self._build_font_group("title", "标题文字"))
        root.addWidget(self._build_font_group("hint", "顶部右侧提示文字"))
        root.addWidget(self._build_font_group("subtitle", "中文字幕"))
        root.addStretch(1)
        return page

    def _build_advanced_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)

        coord_group = QGroupBox("高级坐标设置")
        grid = QGridLayout(coord_group)
        row = 0
        for key, (label, x_attr, y_attr, _, _) in POSITION_TARGETS.items():
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(QLabel("X"), row, 1)
            grid.addWidget(getattr(self, x_attr), row, 2)
            grid.addWidget(QLabel("Y"), row, 3)
            grid.addWidget(getattr(self, y_attr), row, 4)
            row += 1
        root.addWidget(coord_group)

        reference_group = QGroupBox("参考草稿样式接口")
        reference_grid = QGridLayout(reference_group)
        self.reference_draft_edit = self._path_row(reference_grid, 0, "参考草稿目录（可选）", "dir", "")
        root.addWidget(reference_group)

        save_button = QPushButton("保存全部配置")
        save_button.clicked.connect(self._save_config_from_ui)
        root.addWidget(save_button)
        root.addStretch(1)
        return page

    def _build_run_log_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)

        action_layout = QHBoxLayout()
        self.check_button = QPushButton("检查匹配")
        self.generate_button = QPushButton("生成草稿")
        self.open_report_button = QPushButton("打开匹配报告")
        self.open_log_button = QPushButton("打开日志文件")
        self.open_draft_button = QPushButton("打开草稿目录")
        self.clear_log_button = QPushButton("清空日志")

        self.check_button.clicked.connect(self._start_match_check)
        self.generate_button.clicked.connect(self._start_generation)
        self.open_report_button.clicked.connect(self._open_match_report)
        self.open_log_button.clicked.connect(self._open_log_file)
        self.open_draft_button.clicked.connect(self._open_draft_dir)
        self.clear_log_button.clicked.connect(lambda: self.log_view.clear())

        self.action_buttons = [
            self.check_button,
            self.generate_button,
            self.open_report_button,
            self.open_log_button,
            self.open_draft_button,
            self.clear_log_button,
        ]
        for button in self.action_buttons:
            button.setMinimumHeight(40)
            action_layout.addWidget(button)
        action_layout.addStretch(1)
        root.addLayout(action_layout)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("运行日志会显示在这里，同时写入 logs/app.log 和 logs/error.log")
        root.addWidget(self.log_view, 1)
        return page

    def _build_font_group(self, prefix: str, title: str) -> QGroupBox:
        group = QGroupBox(title)
        form = QFormLayout(group)

        font_name = QLineEdit()
        font_name.setPlaceholderText("留空使用剪映默认字体")
        font_size = QDoubleSpinBox()
        font_size.setRange(1.0, 40.0)
        font_size.setSingleStep(0.5)
        font_color = QLineEdit()
        font_color.setPlaceholderText("#000000")
        bold = QCheckBox("加粗")
        italic = QCheckBox("斜体")
        align = QComboBox()
        align.addItem("左对齐", 0)
        align.addItem("居中", 1)
        align.addItem("右对齐", 2)
        stroke_enabled = QCheckBox("启用描边")
        stroke_color = QLineEdit()
        stroke_color.setPlaceholderText("#000000")
        stroke_width = QDoubleSpinBox()
        stroke_width.setRange(0.0, 100.0)
        stroke_width.setSingleStep(5.0)
        shadow_enabled = QCheckBox("启用阴影")

        setattr(self, f"{prefix}_font_name_edit", font_name)
        setattr(self, f"{prefix}_font_size_spin", font_size)
        setattr(self, f"{prefix}_font_color_edit", font_color)
        setattr(self, f"{prefix}_bold_check", bold)
        setattr(self, f"{prefix}_italic_check", italic)
        setattr(self, f"{prefix}_align_combo", align)
        setattr(self, f"{prefix}_stroke_enabled_check", stroke_enabled)
        setattr(self, f"{prefix}_stroke_color_edit", stroke_color)
        setattr(self, f"{prefix}_stroke_width_spin", stroke_width)
        setattr(self, f"{prefix}_shadow_enabled_check", shadow_enabled)

        emphasis_row = QHBoxLayout()
        emphasis_row.addWidget(bold)
        emphasis_row.addWidget(italic)
        emphasis_row.addStretch(1)

        stroke_row = QHBoxLayout()
        stroke_row.addWidget(stroke_enabled)
        stroke_row.addWidget(QLabel("颜色"))
        stroke_row.addWidget(stroke_color)
        stroke_row.addWidget(QLabel("粗细"))
        stroke_row.addWidget(stroke_width)

        form.addRow("字体名称", font_name)
        form.addRow("字号", font_size)
        form.addRow("字体颜色", font_color)
        form.addRow("字形", emphasis_row)
        form.addRow("对齐方式", align)
        form.addRow("描边", stroke_row)
        form.addRow("阴影", shadow_enabled)
        return group

    def _init_position_spins(self) -> None:
        for key, (_, x_attr, y_attr, default_x, default_y) in POSITION_TARGETS.items():
            x_spin = self._spin_box(0, 1920)
            y_spin = self._spin_box(0, 1080)
            x_spin.setValue(default_x)
            y_spin.setValue(default_y)
            x_spin.valueChanged.connect(lambda _value, item=key: self._refresh_position_label(item))
            y_spin.valueChanged.connect(lambda _value, item=key: self._refresh_position_label(item))
            setattr(self, x_attr, x_spin)
            setattr(self, y_attr, y_spin)

    def _build_position_control(self, key: str) -> QGroupBox:
        label, x_attr, y_attr, _, _ = POSITION_TARGETS[key]
        group = QGroupBox(label)
        root = QVBoxLayout(group)

        current_label = QLabel()
        self.position_labels[key] = current_label
        root.addWidget(current_label)

        options = QHBoxLayout()
        step_combo = QComboBox()
        for step in (5, 10, 20, 50):
            step_combo.addItem(f"{step}px", step)
        self.position_step_combos[key] = step_combo
        reset_button = QPushButton("重置默认位置")
        reset_button.clicked.connect(lambda _checked=False, item=key: self._reset_position(item))
        options.addWidget(QLabel("步长"))
        options.addWidget(step_combo)
        options.addWidget(reset_button)
        options.addStretch(1)
        root.addLayout(options)

        buttons = QGridLayout()
        up_button = QPushButton("上移")
        down_button = QPushButton("下移")
        left_button = QPushButton("左移")
        right_button = QPushButton("右移")
        up_button.clicked.connect(lambda _checked=False, item=key: self._nudge_position(item, 0, -1))
        down_button.clicked.connect(lambda _checked=False, item=key: self._nudge_position(item, 0, 1))
        left_button.clicked.connect(lambda _checked=False, item=key: self._nudge_position(item, -1, 0))
        right_button.clicked.connect(lambda _checked=False, item=key: self._nudge_position(item, 1, 0))
        buttons.addWidget(up_button, 0, 1)
        buttons.addWidget(left_button, 1, 0)
        buttons.addWidget(right_button, 1, 2)
        buttons.addWidget(down_button, 2, 1)
        root.addLayout(buttons)

        self._refresh_position_label(key)
        return group

    def _nudge_position(self, key: str, dx: int, dy: int) -> None:
        _, x_attr, y_attr, _, _ = POSITION_TARGETS[key]
        step = int(self.position_step_combos[key].currentData())
        x_spin: QSpinBox = getattr(self, x_attr)
        y_spin: QSpinBox = getattr(self, y_attr)
        x_spin.setValue(x_spin.value() + dx * step)
        y_spin.setValue(y_spin.value() + dy * step)

    def _reset_position(self, key: str) -> None:
        _, x_attr, y_attr, default_x, default_y = POSITION_TARGETS[key]
        getattr(self, x_attr).setValue(default_x)
        getattr(self, y_attr).setValue(default_y)

    def _refresh_position_label(self, key: str) -> None:
        if key not in self.position_labels:
            return
        label, x_attr, y_attr, _, _ = POSITION_TARGETS[key]
        x_value = getattr(self, x_attr).value()
        y_value = getattr(self, y_attr).value()
        self.position_labels[key].setText(f"{label} 当前位置: X={x_value}, Y={y_value}")

    def _spin_box(self, minimum: int, maximum: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(10)
        return spin

    def _path_row(
        self,
        layout: QGridLayout,
        row: int,
        label: str,
        mode: str,
        filter_text: str,
    ) -> QLineEdit:
        edit = QLineEdit()
        button = QPushButton("选择")
        button.clicked.connect(lambda: self._browse_path(edit, mode, filter_text))
        layout.addWidget(QLabel(label), row, 0)
        layout.addWidget(edit, row, 1)
        layout.addWidget(button, row, 2)
        return edit

    def _browse_path(self, edit: QLineEdit, mode: str, filter_text: str) -> None:
        if mode == "dir":
            path = QFileDialog.getExistingDirectory(self, "选择文件夹", edit.text())
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择文件", edit.text(), filter_text)
        if path:
            edit.setText(path)
            if edit is self.excel_edit:
                self._auto_fill_from_excel(Path(path))

    def _load_config_to_ui(self) -> None:
        self.resize(self.config.window_width, self.config.window_height)

        self._safe_set_line_edit("api_key_edit", self.config.api_key)
        self._safe_set_line_edit("endpoint_edit", self.config.bailian_endpoint)
        self._safe_set_line_edit("model_edit", self.config.bailian_model)
        self._safe_set_line_edit("draft_dir_edit", self.config.draft_dir)
        self._safe_set_line_edit("title_text_edit", self.config.title_text)
        self._safe_set_line_edit("hint_text_edit", self.config.hint_text)
        self._safe_set_line_edit("reference_draft_edit", self.config.reference_draft_dir)
        self._safe_set_line_edit("logo_edit", self.config.last_logo_path)
        self._safe_set_line_edit("background_edit", self.config.last_background_path)
        self._safe_set_line_edit("divider_edit", self.config.last_divider_path)

        self.logo_max_size_spin.setValue(self.config.logo_max_size)
        self.illustration_max_width_spin.setValue(self.config.illustration_max_width)
        self.illustration_max_height_spin.setValue(self.config.illustration_max_height)
        
        self.logo_x_spin.setValue(self.config.logo_x)
        self.logo_y_spin.setValue(self.config.logo_y)
        self.title_x_spin.setValue(self.config.title_x)
        self.title_y_spin.setValue(self.config.title_y)
        self.hint_x_spin.setValue(self.config.hint_x)
        self.hint_y_spin.setValue(self.config.hint_y)
        self.illustration_center_x_spin.setValue(self.config.illustration_center_x)
        self.illustration_center_y_spin.setValue(self.config.illustration_center_y)
        self._set_combo_by_data(
            self.illustration_fusion_combo,
            self.config.illustration_fusion_mode,
            ILLUSTRATION_MODE_PRECOMPOSE_DARKEN,
        )
        self.divider_center_x_spin.setValue(self.config.divider_center_x)
        self.divider_center_y_spin.setValue(self.config.divider_center_y)
        self.subtitle_center_x_spin.setValue(self.config.subtitle_center_x)
        self.subtitle_center_y_spin.setValue(self.config.subtitle_center_y)

        for prefix in ("title", "hint", "subtitle"):
            self._load_font_style_to_ui(prefix)


    def _safe_set_line_edit(self, attr_name: str, value: str) -> None:
        widget = getattr(self, attr_name, None)
        if isinstance(widget, QLineEdit):
            widget.setText(value)
        else:
            logger.warning("控件 %s 不存在或不是 QLineEdit，跳过配置回填", attr_name)

    def _load_font_style_to_ui(self, prefix: str) -> None:
        getattr(self, f"{prefix}_font_name_edit").setText(getattr(self.config, f"{prefix}_font_name"))
        getattr(self, f"{prefix}_font_size_spin").setValue(float(getattr(self.config, f"{prefix}_font_size")))
        getattr(self, f"{prefix}_font_color_edit").setText(getattr(self.config, f"{prefix}_font_color"))
        getattr(self, f"{prefix}_bold_check").setChecked(bool(getattr(self.config, f"{prefix}_bold")))
        getattr(self, f"{prefix}_italic_check").setChecked(bool(getattr(self.config, f"{prefix}_italic")))
        self._set_combo_by_data(
            getattr(self, f"{prefix}_align_combo"),
            int(getattr(self.config, f"{prefix}_align")),
            1,
        )
        getattr(self, f"{prefix}_stroke_enabled_check").setChecked(
            bool(getattr(self.config, f"{prefix}_stroke_enabled"))
        )
        getattr(self, f"{prefix}_stroke_color_edit").setText(getattr(self.config, f"{prefix}_stroke_color"))
        getattr(self, f"{prefix}_stroke_width_spin").setValue(
            float(getattr(self.config, f"{prefix}_stroke_width"))
        )
        getattr(self, f"{prefix}_shadow_enabled_check").setChecked(
            bool(getattr(self.config, f"{prefix}_shadow_enabled"))
        )

    def _set_combo_by_data(self, combo: QComboBox, value: Any, default: Any) -> None:
        index = combo.findData(value)
        if index < 0:
            index = combo.findData(default)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _save_config_from_ui(self) -> None:
        self.config = self._collect_config()
        save_config(self.config)
        self._append_log("配置已保存")

    def _layout_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {
            "divider_center_x": self.divider_center_x_spin.value(),
            "divider_center_y": self.divider_center_y_spin.value(),
            "logo_x": self.logo_x_spin.value(),
            "logo_y": self.logo_y_spin.value(),
            "illustration_max_width": self.illustration_max_width_spin.value(),
            "illustration_max_height": self.illustration_max_height_spin.value(),
            "illustration_center_x": self.illustration_center_x_spin.value(),
            "illustration_center_y": self.illustration_center_y_spin.value(),
            "logo_max_size": self.logo_max_size_spin.value(),
            "title_x": self.title_x_spin.value(),
            "title_y": self.title_y_spin.value(),
            "hint_x": self.hint_x_spin.value(),
            "hint_y": self.hint_y_spin.value(),
            "subtitle_center_x": self.subtitle_center_x_spin.value(),
            "subtitle_center_y": self.subtitle_center_y_spin.value(),
            "illustration_fusion_mode": str(self.illustration_fusion_combo.currentData()),
        }
        for prefix in ("title", "hint", "subtitle"):
            values.update(self._font_values(prefix))
        return values

    def _font_values(self, prefix: str) -> dict[str, Any]:
        return {
            f"{prefix}_font_name": getattr(self, f"{prefix}_font_name_edit").text().strip(),
            f"{prefix}_font_size": getattr(self, f"{prefix}_font_size_spin").value(),
            f"{prefix}_font_color": getattr(self, f"{prefix}_font_color_edit").text().strip() or "#000000",
            f"{prefix}_bold": getattr(self, f"{prefix}_bold_check").isChecked(),
            f"{prefix}_italic": getattr(self, f"{prefix}_italic_check").isChecked(),
            f"{prefix}_align": int(getattr(self, f"{prefix}_align_combo").currentData()),
            f"{prefix}_stroke_enabled": getattr(self, f"{prefix}_stroke_enabled_check").isChecked(),
            f"{prefix}_stroke_color": getattr(self, f"{prefix}_stroke_color_edit").text().strip() or "#000000",
            f"{prefix}_stroke_width": getattr(self, f"{prefix}_stroke_width_spin").value(),
            f"{prefix}_shadow_enabled": getattr(self, f"{prefix}_shadow_enabled_check").isChecked(),
        }

    def _collect_config(self) -> AppConfig:
        return AppConfig(
            api_key=self.api_key_edit.text().strip(),
            bailian_endpoint=self.endpoint_edit.text().strip(),
            bailian_model=self.model_edit.text().strip(),
            draft_dir=self.draft_dir_edit.text().strip(),
            title_text=self.title_text_edit.text().strip() or "魔王心理学",
            hint_text=self.hint_text_edit.text().strip() or "看懂关系，也看懂自己",
            reference_draft_dir=self.reference_draft_edit.text().strip(),
            last_logo_path=self.logo_edit.text().strip(),
            last_background_path=self.background_edit.text().strip(),
            last_divider_path=self.divider_edit.text().strip(),
            window_width=self.width(),
            window_height=self.height(),
            **self._layout_values(),
        )

    def _validate_api(self) -> None:
        config = self._collect_config()
        try:
            ok = BailianClient(
                api_key=config.api_key,
                endpoint=config.bailian_endpoint,
                model=config.bailian_model,
                timeout=20,
            ).validate()
        except Exception as exc:
            QMessageBox.critical(self, "验证失败", str(exc))
            return
        QMessageBox.information(self, "验证成功", "百炼 API Key 可用" if ok else "百炼 API 返回异常")

    def _start_generation(self) -> None:
        try:
            self.config = self._collect_config()
            save_config(self.config)
            inputs = self._collect_inputs(require_generation_assets=True)
        except Exception as exc:
            QMessageBox.critical(self, "输入不完整", str(exc))
            return

        self._start_worker("generate", inputs, "开始生成草稿...")

    def _start_match_check(self) -> None:
        try:
            self.config = self._collect_config()
            save_config(self.config)
            inputs = self._collect_inputs(require_generation_assets=False)
        except Exception as exc:
            QMessageBox.critical(self, "输入不完整", str(exc))
            return

        self._start_worker("check", inputs, "开始检查匹配...")

    def _start_worker(self, mode: str, inputs: GenerationInputs, message: str) -> None:
        self._set_worker_buttons_enabled(False)
        self._append_log(message)
        self.worker_thread = QThread(self)
        self.worker = GenerationWorker(self.config, inputs, mode)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._append_log)
        self.worker.finished.connect(self._worker_finished)
        self.worker.failed.connect(self._worker_failed)
        self.worker.finished.connect(lambda *_: self.worker_thread.quit())
        self.worker.failed.connect(lambda *_: self.worker_thread.quit())
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _collect_inputs(self, require_generation_assets: bool) -> GenerationInputs:
        def required_path(edit: QLineEdit, label: str, must_be_dir: bool = False) -> Path:
            text = edit.text().strip()
            if not text:
                raise ValueError(f"请填写 {label}")
            path = Path(text)
            if not path.exists():
                raise ValueError(f"{label} 不存在: {path}")
            if must_be_dir and not path.is_dir():
                raise ValueError(f"{label} 不是文件夹: {path}")
            if not must_be_dir and not path.is_file():
                raise ValueError(f"{label} 不是文件: {path}")
            return path

        def optional_path(edit: QLineEdit, label: str, must_be_dir: bool = False) -> Path | None:
            text = edit.text().strip()
            if not text:
                return None
            path = Path(text)
            if not path.exists():
                raise ValueError(f"{label} 不存在: {path}")
            if must_be_dir and not path.is_dir():
                raise ValueError(f"{label} 不是文件夹: {path}")
            if not must_be_dir and not path.is_file():
                raise ValueError(f"{label} 不是文件: {path}")
            return path

        audio_path = required_path(self.audio_edit, "配音文件") if require_generation_assets else Path()
        logo_path = required_path(self.logo_edit, "Logo 图片") if require_generation_assets else Path()
        draft_dir_text = self.draft_dir_edit.text().strip() or self.config.draft_dir
        draft_dir = Path(draft_dir_text)
        if require_generation_assets:
            if not draft_dir.exists():
                raise ValueError(f"剪映草稿目录不存在: {draft_dir}")
            if not draft_dir.is_dir():
                raise ValueError(f"剪映草稿目录不是文件夹: {draft_dir}")

        reference_draft_dir = optional_path(self.reference_draft_edit, "参考草稿目录", True)

        return GenerationInputs(
            excel_path=required_path(self.excel_edit, "Excel 分镜文件"),
            srt_path=required_path(self.srt_edit, "SRT 中文字幕文件"),
            audio_path=audio_path,
            image_dir=required_path(self.image_dir_edit, "图片文件夹", True),
            logo_path=logo_path,
            background_path=optional_path(self.background_edit, "背景图") if require_generation_assets else None,
            divider_path=required_path(self.divider_edit, "黑色分割线图片") if require_generation_assets else None,
            draft_dir=draft_dir,
            output_name=self.output_name_edit.text().strip(),
            title_text=self.title_text_edit.text().strip() or "魔王心理学",
            hint_text=self.hint_text_edit.text().strip() or "看懂关系，也看懂自己",
            reference_draft_dir=reference_draft_dir,
            template_draft_dir=reference_draft_dir,
            **self._layout_values(),
        )

    def _worker_finished(self, mode: str, output_path: str, report_path: str) -> None:
        self._set_worker_buttons_enabled(True)
        if report_path:
            self.last_report_path = Path(report_path)
        if mode == "check":
            self._append_log(f"检查完成: {output_path}")
            QMessageBox.information(self, "完成", f"匹配报告已生成:\n{output_path}")
        else:
            self.last_draft_dir = Path(output_path)
            self._append_log(f"生成完成: {output_path}")
            QMessageBox.information(self, "完成", f"草稿目录已生成:\n{output_path}")

    def _worker_failed(self, message: str) -> None:
        self._set_worker_buttons_enabled(True)
        self._append_log(f"任务失败: {message}")
        QMessageBox.critical(self, "任务失败", message)

    def _set_worker_buttons_enabled(self, enabled: bool) -> None:
        for button in self.action_buttons:
            button.setEnabled(enabled)

    def _open_match_report(self) -> None:
        if not self.last_report_path or not self.last_report_path.exists():
            QMessageBox.information(self, "没有匹配报告", "还没有生成匹配报告，请先点击“检查匹配”。")
            return
        self._open_path(self.last_report_path)

    def _open_log_file(self) -> None:
        path = log_dir() / "app.log"
        if not path.exists():
            QMessageBox.information(self, "没有日志文件", "当前还没有运行日志文件。")
            return
        self._open_path(path)

    def _open_draft_dir(self) -> None:
        if self.last_draft_dir and self.last_draft_dir.exists():
            self._open_path(self.last_draft_dir)
            return
        draft_dir = Path(self.draft_dir_edit.text().strip() or self.config.draft_dir)
        if not draft_dir.exists():
            QMessageBox.information(self, "目录不存在", f"剪映草稿目录不存在:\n{draft_dir}")
            return
        self._open_path(draft_dir)

    def _open_path(self, path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))


    def _build_log_tab(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        log_tip = QLabel("日志已在“生成草稿”页实时显示；可使用下方按钮复制或清空。")
        root.addWidget(log_tip)
        return page

    def _auto_fill_from_excel(self, excel_path: Path) -> None:
        folder = excel_path.parent
        stem = excel_path.stem
        self._append_log(f"自动匹配：Excel 所在目录 {folder}")
        self.output_name_edit.setText(stem)

        def best(paths, exts_label):
            if not paths:
                return None, f"未找到{exts_label}"
            if len(paths) == 1:
                return paths[0], f"仅找到一个{exts_label}"
            scored = sorted(paths, key=lambda p: difflib.SequenceMatcher(None, stem.lower(), p.stem.lower()).ratio(), reverse=True)
            if scored:
                top = scored[0]
                if len(scored) == 1 or difflib.SequenceMatcher(None, stem.lower(), top.stem.lower()).ratio() > 0:
                    return top, "按文件名相似度最高"
            latest = max(paths, key=lambda p: p.stat().st_mtime)
            return latest, "相似度无法区分，按最新修改时间"

        srt_candidates = [p for p in folder.iterdir() if p.suffix.lower() == '.srt']
        self._append_log('SRT 候选: ' + ', '.join(p.name for p in srt_candidates) if srt_candidates else 'SRT 候选: 无')
        srt, reason = best(srt_candidates, 'SRT')
        if srt:
            self.srt_edit.setText(str(srt))
            self._append_log(f"自动选择 SRT: {srt.name}（{reason}）")

        audio_candidates = [p for p in folder.iterdir() if p.suffix.lower() in {'.wav','.mp3','.m4a','.aac'}]
        self._append_log('音频候选: ' + ', '.join(p.name for p in audio_candidates) if audio_candidates else '音频候选: 无')
        audio, reason = best(audio_candidates, '音频')
        if audio:
            self.audio_edit.setText(str(audio))
            self._append_log(f"自动选择音频: {audio.name}（{reason}）")

        image_candidates = [p for p in folder.iterdir() if p.suffix.lower() in {'.png','.jpg','.jpeg','.webp'}]
        divider_keywords = ['分割线','黑线','横线','divider','line']
        divider = next((p for p in image_candidates if any(k in p.stem.lower() for k in divider_keywords)), None)
        if divider:
            self.divider_edit.setText(str(divider))
            self._append_log(f"自动选择黑色分割线图片: {divider.name}（关键词匹配）")
        else:
            self._append_log('未找到黑色分割线图片，需要手动选择')

        bg = next((p for p in image_candidates if any(k in p.stem.lower() for k in ['背景','background','bg'])), None)
        if bg:
            self.background_edit.setText(str(bg))
            self._append_log(f"自动选择背景图: {bg.name}")
        else:
            self._append_log('未找到背景图，保持为空')

        if not self.logo_edit.text().strip() and getattr(self.config, 'last_logo_path', ''):
            self.logo_edit.setText(self.config.last_logo_path)

        self._append_log('需要手动选择：图片文件夹（必填）')

    def _append_log(self, message: str) -> None:
        self.log_view.append(message)
