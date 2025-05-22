import sys
import cv2
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QPushButton, QLabel, QListWidget, QGroupBox, QDialog,
                            QLineEdit, QFormLayout, QMessageBox, QSlider, QInputDialog, QFileDialog)
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QMouseEvent, QIcon
import sounddevice as sd
import soundfile as sf
import shutil
import ffmpeg
from PIL import Image

from screen_capture import ScreenCapture
from audio_capture import AudioCapture
from stream_manager import StreamManager
from scene_manager import SceneManager, Scene, Source

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stream Settings")
        self.setModal(True)
        layout = QFormLayout(self)
        self.stream_url = QLineEdit()
        self.stream_key = QLineEdit()
        layout.addRow("Stream URL:", self.stream_url)
        layout.addRow("Stream Key:", self.stream_key)
        buttons = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("Cancel")
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(ok_button)
        buttons.addWidget(cancel_button)
        layout.addRow(buttons)

class MixerWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.desktop_label = QLabel("Desktop Audio")
        self.desktop_slider = QSlider(Qt.Orientation.Horizontal)
        self.desktop_slider.setRange(0, 100)
        self.desktop_slider.setValue(0)
        self.mic_label = QLabel("Mic/Aux")
        self.mic_slider = QSlider(Qt.Orientation.Horizontal)
        self.mic_slider.setRange(0, 100)
        self.mic_slider.setValue(0)
        layout.addWidget(self.desktop_label)
        layout.addWidget(self.desktop_slider)
        layout.addWidget(self.mic_label)
        layout.addWidget(self.mic_slider)
        layout.addStretch()
        # Таймер для обновления VU-метра
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_mic_level)
        self.timer.start(100)
        self.stream = None
        self.start_mic_stream()

    def start_mic_stream(self):
        try:
            self.stream = sd.InputStream(callback=self.audio_callback, channels=1, samplerate=44100)
            self.stream.start()
        except Exception:
            self.stream = None

    def audio_callback(self, indata, frames, time, status):
        self.level = int(np.linalg.norm(indata) * 100)

    def update_mic_level(self):
        # Обновляем VU-метр микрофона
        level = getattr(self, 'level', 0)
        self.mic_slider.setValue(min(level, 100))
        # Desktop Audio — пока заглушка
        self.desktop_slider.setValue(0)

class PreviewWidget(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.selected_source = None
        self.dragging = False
        self.resizing = False
        self.drag_offset = QPoint(0, 0)
        self.resize_dir = None
        self.sources = []
        self.preview_image = None
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.offset_x = 0
        self.offset_y = 0

    def set_preview(self, image, sources):
        self.preview_image = image
        self.sources = sources
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.preview_image is not None:
            h, w, ch = self.preview_image.shape
            bytes_per_line = ch * w
            qt_image = QImage(self.preview_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)
            label_size = self.size()
            scaled_pixmap = pixmap.scaled(label_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            painter = QPainter(self)
            # Центрирование
            x = (label_size.width() - scaled_pixmap.width()) // 2
            y = (label_size.height() - scaled_pixmap.height()) // 2
            self.scale_x = scaled_pixmap.width() / w
            self.scale_y = scaled_pixmap.height() / h
            self.offset_x = x
            self.offset_y = y
            painter.drawPixmap(x, y, scaled_pixmap)
            for src in self.sources:
                pos = src.position
                size = src.size
                rx = int(pos[0] * self.scale_x) + x
                ry = int(pos[1] * self.scale_y) + y
                rw = int(size[0] * self.scale_x)
                rh = int(size[1] * self.scale_y)
                if src == self.selected_source:
                    pen = QPen(QColor(255, 255, 0), 2)
                else:
                    pen = QPen(QColor(0, 200, 255), 2)
                painter.setPen(pen)
                painter.drawRect(QRect(rx, ry, rw, rh))
                # Уголки для resize
                if src == self.selected_source:
                    painter.setBrush(QColor(255,255,0))
                    for cx, cy in [(rx, ry), (rx+rw, ry), (rx, ry+rh), (rx+rw, ry+rh)]:
                        painter.drawRect(cx-3, cy-3, 6, 6)
            painter.end()

    def mousePressEvent(self, event):
        if not self.sources:
            return
        pos = event.position() if hasattr(event, 'position') else event.pos()
        x, y = int(pos.x()), int(pos.y())
        for src in reversed(self.sources):  # Сначала верхние
            rx = int(src.position[0] * self.scale_x) + self.offset_x
            ry = int(src.position[1] * self.scale_y) + self.offset_y
            rw = int(src.size[0] * self.scale_x)
            rh = int(src.size[1] * self.scale_y)
            # Проверка на resize (уголки)
            for idx, (cx, cy) in enumerate([(rx, ry), (rx+rw, ry), (rx, ry+rh), (rx+rw, ry+rh)]):
                if abs(x-cx)<=6 and abs(y-cy)<=6:
                    self.selected_source = src
                    self.resizing = True
                    self.resize_dir = idx
                    self.drag_offset = QPoint(x-cx, y-cy)
                    self.update()
                    return
            # Проверка на drag
            if rx <= x <= rx+rw and ry <= y <= ry+rh:
                self.selected_source = src
                self.dragging = True
                self.drag_offset = QPoint(x-rx, y-ry)
                self.update()
                return
        self.selected_source = None
        self.update()

    def mouseMoveEvent(self, event):
        if not self.selected_source:
            return
        pos = event.position() if hasattr(event, 'position') else event.pos()
        x, y = int(pos.x()), int(pos.y())
        src = self.selected_source
        if self.dragging:
            new_x = int((x - self.drag_offset.x() - self.offset_x) / self.scale_x)
            new_y = int((y - self.drag_offset.y() - self.offset_y) / self.scale_y)
            src.position = (max(0, new_x), max(0, new_y))
            self.update()
        elif self.resizing:
            px = int(src.position[0] * self.scale_x) + self.offset_x
            py = int(src.position[1] * self.scale_y) + self.offset_y
            pw = int(src.size[0] * self.scale_x)
            ph = int(src.size[1] * self.scale_y)
            if self.resize_dir == 0:  # top-left
                new_w = pw + (px - x)
                new_h = ph + (py - y)
                new_x = int((x - self.offset_x) / self.scale_x)
                new_y = int((y - self.offset_y) / self.scale_y)
                if new_w > 10 and new_h > 10:
                    src.position = (new_x, new_y)
                    src.size = (new_w//self.scale_x, new_h//self.scale_y)
            elif self.resize_dir == 1:  # top-right
                new_w = x - px
                new_h = ph + (py - y)
                new_y = int((y - self.offset_y) / self.scale_y)
                if new_w > 10 and new_h > 10:
                    src.size = (new_w//self.scale_x, new_h//self.scale_y)
                    src.position = (src.position[0], new_y)
            elif self.resize_dir == 2:  # bottom-left
                new_w = pw + (px - x)
                new_h = y - py
                new_x = int((x - self.offset_x) / self.scale_x)
                if new_w > 10 and new_h > 10:
                    src.position = (new_x, src.position[1])
                    src.size = (new_w//self.scale_x, new_h//self.scale_y)
            elif self.resize_dir == 3:  # bottom-right
                new_w = x - px
                new_h = y - py
                if new_w > 10 and new_h > 10:
                    src.size = (new_w//self.scale_x, new_h//self.scale_y)
            self.update()

    def mouseReleaseEvent(self, event):
        self.dragging = False
        self.resizing = False
        self.resize_dir = None

class RPYMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTP - Record Tool Python")
        self.setGeometry(100, 100, 1280, 800)
        self.setStyleSheet(self.dark_style())
        self.screen_capture = ScreenCapture()
        self.audio_capture = AudioCapture()
        self.stream_manager = StreamManager()
        self.scene_manager = SceneManager()
        # --- Основной layout ---
        central = QWidget()
        self.setCentralWidget(central)
        main_v = QVBoxLayout(central)
        # --- Верх: предпросмотр ---
        self.preview_label = PreviewWidget()
        self.preview_label.setMinimumSize(900, 500)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_box = QGroupBox()
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.addWidget(self.preview_label)
        main_v.addWidget(preview_box, stretch=3)
        # --- Низ: три колонки ---
        bottom_h = QHBoxLayout()
        # Сцены
        scenes_box = QGroupBox("Scenes")
        scenes_layout = QVBoxLayout(scenes_box)
        self.scenes_list = QListWidget()
        self.scenes_list.itemClicked.connect(self.scene_selected)
        scenes_layout.addWidget(self.scenes_list)
        scenes_btns = QHBoxLayout()
        self.add_scene_btn = QPushButton("+")
        self.remove_scene_btn = QPushButton("-")
        self.add_scene_btn.clicked.connect(self.add_scene)
        self.remove_scene_btn.clicked.connect(self.remove_scene)
        scenes_btns.addWidget(self.add_scene_btn)
        scenes_btns.addWidget(self.remove_scene_btn)
        scenes_layout.addLayout(scenes_btns)
        bottom_h.addWidget(scenes_box, stretch=1)
        # Источники
        sources_box = QGroupBox("Источники")
        sources_layout = QVBoxLayout(sources_box)
        self.sources_list = QListWidget()
        self.sources_list.itemClicked.connect(self.source_selected)
        sources_layout.addWidget(self.sources_list)
        sources_btns = QHBoxLayout()
        self.add_source_btn = QPushButton("+")
        self.remove_source_btn = QPushButton("-")
        self.up_source_btn = QPushButton("↑")
        self.down_source_btn = QPushButton("↓")
        self.toggle_visible_btn = QPushButton()
        self.toggle_visible_btn.setIcon(QIcon.fromTheme("view-visible"))
        self.add_source_btn.clicked.connect(self.add_source)
        self.remove_source_btn.clicked.connect(self.remove_source)
        self.up_source_btn.clicked.connect(self.move_source_up)
        self.down_source_btn.clicked.connect(self.move_source_down)
        self.toggle_visible_btn.clicked.connect(self.toggle_source_visible)
        sources_btns.addWidget(self.add_source_btn)
        sources_btns.addWidget(self.remove_source_btn)
        sources_btns.addWidget(self.up_source_btn)
        sources_btns.addWidget(self.down_source_btn)
        sources_btns.addWidget(self.toggle_visible_btn)
        sources_layout.addLayout(sources_btns)
        bottom_h.addWidget(sources_box, stretch=2)
        # Микшер
        mixer_box = QGroupBox("Микшер")
        mixer_layout = QVBoxLayout(mixer_box)
        self.mixer = MixerWidget()
        mixer_layout.addWidget(self.mixer)
        bottom_h.addWidget(mixer_box, stretch=2)
        main_v.addLayout(bottom_h, stretch=1)
        # --- Управление справа внизу ---
        controls_h = QHBoxLayout()
        controls_h.addStretch()
        self.start_stream_btn = QPushButton("Начать трансляцию")
        self.stop_stream_btn = QPushButton("Остановить трансляцию")
        self.stream_settings_btn = QPushButton("Настройки")
        self.start_record_btn = QPushButton("Запись")
        self.stop_record_btn = QPushButton("Стоп запись")
        self.screenshot_btn = QPushButton("Скриншот")
        self.export_btn = QPushButton("Экспорт профиля")
        self.import_btn = QPushButton("Импорт профиля")
        self.fade_btn = QPushButton("Fade переход")
        self.cut_btn = QPushButton("Cut переход")
        self.start_stream_btn.clicked.connect(self.start_streaming)
        self.stop_stream_btn.clicked.connect(self.stop_streaming)
        self.stream_settings_btn.clicked.connect(self.show_stream_settings)
        self.start_record_btn.clicked.connect(self.start_recording)
        self.stop_record_btn.clicked.connect(self.stop_recording)
        self.screenshot_btn.clicked.connect(self.save_screenshot)
        self.export_btn.clicked.connect(self.export_profile)
        self.import_btn.clicked.connect(self.import_profile)
        self.fade_btn.clicked.connect(lambda: self.switch_scene('fade'))
        self.cut_btn.clicked.connect(lambda: self.switch_scene('cut'))
        controls_h.addWidget(self.start_stream_btn)
        controls_h.addWidget(self.stop_stream_btn)
        controls_h.addWidget(self.start_record_btn)
        controls_h.addWidget(self.stop_record_btn)
        controls_h.addWidget(self.screenshot_btn)
        controls_h.addWidget(self.export_btn)
        controls_h.addWidget(self.import_btn)
        controls_h.addWidget(self.fade_btn)
        controls_h.addWidget(self.cut_btn)
        controls_h.addWidget(self.stream_settings_btn)
        main_v.addLayout(controls_h)
        # --- Таймер предпросмотра ---
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.update_preview)
        self.preview_timer.start(33)
        # Если сцен нет после загрузки — создать первую сцену
        if not self.scene_manager.scenes:
            self.create_initial_scene()
        self.screen_capture.start_capture()

    def dark_style(self):
        return """
        QMainWindow, QWidget, QGroupBox, QListWidget, QLabel, QPushButton {
            background-color: #181e23;
            color: #c7d0d9;
            font-size: 14px;
        }
        QGroupBox {
            border: 1px solid #23272e;
            margin-top: 10px;
        }
        QGroupBox:title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 3px 0 3px;
        }
        QPushButton {
            background-color: #23272e;
            border: 1px solid #23272e;
            border-radius: 3px;
            padding: 4px 10px;
        }
        QPushButton:hover {
            background-color: #2c313a;
        }
        QListWidget {
            background-color: #23272e;
            border: none;
        }
        QSlider::groove:horizontal {
            border: 1px solid #23272e;
            height: 6px;
            background: #23272e;
        }
        QSlider::handle:horizontal {
            background: #c7d0d9;
            border: 1px solid #23272e;
            width: 12px;
            margin: -4px 0;
            border-radius: 6px;
        }
        """

    def create_initial_scene(self):
        scene = self.scene_manager.create_scene("Main Scene")
        self.scene_manager.set_active_scene(scene.id)
        self.update_scenes_list()
        self.scene_manager.add_source(
            scene.id,
            'screen',
            'Screen Capture',
            {'display': 0}
        )
        self.update_sources_list()

    def update_scenes_list(self):
        self.scenes_list.clear()
        for scene in self.scene_manager.scenes:
            self.scenes_list.addItem(scene.name)

    def update_sources_list(self):
        self.sources_list.clear()
        if self.scene_manager.current_scene:
            for source in self.scene_manager.current_scene.sources:
                name = source.name
                if not source.visible:
                    name = "[скрыт] " + name
                self.sources_list.addItem(name)

    def scene_selected(self, item):
        scene_name = item.text()
        for scene in self.scene_manager.scenes:
            if scene.name == scene_name:
                self.scene_manager.set_active_scene(scene.id)
                self.update_sources_list()
                break

    def source_selected(self, item):
        pass

    def add_scene(self):
        scene = self.scene_manager.create_scene(f"Scene {len(self.scene_manager.scenes) + 1}")
        self.update_scenes_list()

    def remove_scene(self):
        current_item = self.scenes_list.currentItem()
        if current_item:
            scene_name = current_item.text()
            for scene in self.scene_manager.scenes:
                if scene.name == scene_name:
                    self.scene_manager.delete_scene(scene.id)
                    self.update_scenes_list()
                    self.update_sources_list()
                    break

    def add_source(self):
        if not self.scene_manager.current_scene:
            return
        # Диалог выбора типа источника
        source_types = ["Захват экрана", "Захват окна", "Изображение", "Видео", "Браузер"]
        source_type, ok = QInputDialog.getItem(self, "Тип источника", "Выберите тип источника:", source_types, 0, False)
        if not ok:
            return
        if source_type == "Захват экрана":
            source = self.scene_manager.add_source(
                self.scene_manager.current_scene.id,
                'screen',
                f"Screen Capture {len(self.scene_manager.current_scene.sources) + 1}",
                {'display': 0}
            )
        elif source_type == "Захват окна":
            windows = self.screen_capture.get_available_windows()
            if not windows:
                QMessageBox.warning(self, "Нет окон", "Нет доступных окон для захвата.")
                return
            window_title, ok = QInputDialog.getItem(self, "Выбор окна", "Выберите окно:", windows, 0, False)
            if not ok:
                return
            source = self.scene_manager.add_source(
                self.scene_manager.current_scene.id,
                'window',
                f"Window Capture {len(self.scene_manager.current_scene.sources) + 1}",
                {'window_title': window_title}
            )
        elif source_type == "Изображение":
            file, ok = QFileDialog.getOpenFileName(self, "Выберите изображение", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
            if not ok or not file:
                return
            source = self.scene_manager.add_source(
                self.scene_manager.current_scene.id,
                'image',
                f"Image {len(self.scene_manager.current_scene.sources) + 1}",
                {'file': file}
            )
        elif source_type == "Видео":
            file, ok = QFileDialog.getOpenFileName(self, "Выберите видео", "", "Videos (*.mp4 *.avi *.mkv *.mov)")
            if not ok or not file:
                return
            source = self.scene_manager.add_source(
                self.scene_manager.current_scene.id,
                'video',
                f"Video {len(self.scene_manager.current_scene.sources) + 1}",
                {'file': file}
            )
        elif source_type == "Браузер":
            url, ok = QInputDialog.getText(self, "URL", "Введите URL:")
            if not ok or not url:
                return
            source = self.scene_manager.add_source(
                self.scene_manager.current_scene.id,
                'browser',
                f"Browser {len(self.scene_manager.current_scene.sources) + 1}",
                {'url': url}
            )
        self.update_sources_list()

    def remove_source(self):
        if not self.scene_manager.current_scene:
            return
        current_item = self.sources_list.currentItem()
        if current_item:
            source_name = current_item.text()
            for source in self.scene_manager.current_scene.sources:
                if source.name == source_name:
                    self.scene_manager.remove_source(
                        self.scene_manager.current_scene.id,
                        source.id
                    )
                    self.update_sources_list()
                    break

    def show_stream_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.stream_url = dialog.stream_url.text()
            self.stream_key = dialog.stream_key.text()

    def start_streaming(self):
        if not hasattr(self, 'stream_url') or not hasattr(self, 'stream_key'):
            QMessageBox.warning(self, "Error", "Please configure stream settings first")
            return
        self.stream_manager.start_stream(self.stream_url, self.stream_key)
        self.start_stream_btn.setEnabled(False)
        self.stop_stream_btn.setEnabled(True)

    def stop_streaming(self):
        self.stream_manager.stop_stream()
        self.start_stream_btn.setEnabled(True)
        self.stop_stream_btn.setEnabled(False)

    def start_recording(self):
        file, ok = QFileDialog.getSaveFileName(self, "Сохранить запись", "record.mp4", "MP4 (*.mp4)")
        if not ok or not file:
            return
        self.recording = True
        self.record_file = file
        self.record_frames = []
        self.start_record_btn.setEnabled(False)
        self.stop_record_btn.setEnabled(True)

    def stop_recording(self):
        self.recording = False
        self.start_record_btn.setEnabled(True)
        self.stop_record_btn.setEnabled(False)
        if hasattr(self, 'record_frames') and self.record_frames:
            # Сохраняем в mp4 через ffmpeg-python
            h, w, _ = self.record_frames[0].shape
            process = (
                ffmpeg
                .input('pipe:', format='rawvideo', pix_fmt='bgr24', s=f'{w}x{h}', framerate=30)
                .output(self.record_file, pix_fmt='yuv420p', vcodec='libx264', r=30)
                .overwrite_output()
                .run_async(pipe_stdin=True)
            )
            for frame in self.record_frames:
                process.stdin.write(frame.astype(np.uint8).tobytes())
            process.stdin.close()
            process.wait()

    def update_preview(self):
        if self.scene_manager.current_scene:
            preview = self.scene_manager.get_scene_preview(self.scene_manager.current_scene.id)
            if preview is not None:
                self.preview_label.set_preview(preview, self.scene_manager.current_scene.sources)
                # Для записи
                if getattr(self, 'recording', False):
                    self.record_frames.append(preview.copy())

    def move_source_up(self):
        scene = self.scene_manager.current_scene
        idx = self.sources_list.currentRow()
        if scene and 0 < idx < len(scene.sources):
            scene.sources[idx-1], scene.sources[idx] = scene.sources[idx], scene.sources[idx-1]
            self.update_sources_list()

    def move_source_down(self):
        scene = self.scene_manager.current_scene
        idx = self.sources_list.currentRow()
        if scene and 0 <= idx < len(scene.sources)-1:
            scene.sources[idx+1], scene.sources[idx] = scene.sources[idx], scene.sources[idx+1]
            self.update_sources_list()

    def toggle_source_visible(self):
        scene = self.scene_manager.current_scene
        idx = self.sources_list.currentRow()
        if scene and 0 <= idx < len(scene.sources):
            scene.sources[idx].visible = not scene.sources[idx].visible
            self.update_sources_list()

    def export_profile(self):
        file, ok = QFileDialog.getSaveFileName(self, "Экспорт профиля", "profile.json", "JSON (*.json)")
        if ok and file:
            shutil.copyfile(self.scene_manager.config_path, file)

    def import_profile(self):
        file, ok = QFileDialog.getOpenFileName(self, "Импорт профиля", "", "JSON (*.json)")
        if ok and file:
            shutil.copyfile(file, self.scene_manager.config_path)
            self.scene_manager.load_config()
            self.update_scenes_list()
            self.update_sources_list()

    def save_screenshot(self):
        file, ok = QFileDialog.getSaveFileName(self, "Сохранить скриншот", "screenshot.png", "PNG (*.png)")
        if ok and file:
            if self.scene_manager.current_scene:
                preview = self.scene_manager.get_scene_preview(self.scene_manager.current_scene.id)
                img = Image.fromarray(cv2.cvtColor(preview, cv2.COLOR_BGR2RGB))
                img.save(file)

    def switch_scene(self, mode):
        # mode: 'fade' или 'cut'
        if not self.scene_manager.scenes:
            return
        idx = self.scenes_list.currentRow()
        if idx < 0 or idx >= len(self.scene_manager.scenes):
            return
        target_scene = self.scene_manager.scenes[idx]
        if mode == 'cut':
            self.scene_manager.set_active_scene(target_scene.id)
            self.update_sources_list()
        elif mode == 'fade':
            # Плавный переход (fade)
            if self.scene_manager.current_scene:
                from_scene = self.scene_manager.current_scene
                to_scene = target_scene
                steps = 10
                for alpha in np.linspace(0, 1, steps):
                    from_img = self.scene_manager.get_scene_preview(from_scene.id).astype(np.float32)
                    to_img = self.scene_manager.get_scene_preview(to_scene.id).astype(np.float32)
                    blend = cv2.addWeighted(from_img, 1-alpha, to_img, alpha, 0).astype(np.uint8)
                    self.preview_label.set_preview(blend, to_scene.sources)
                    QApplication.processEvents()
                self.scene_manager.set_active_scene(target_scene.id)
                self.update_sources_list()

    def closeEvent(self, event):
        self.scene_manager.save_config()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RPYMainWindow()
    window.show()
    sys.exit(app.exec())
