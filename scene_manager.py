from dataclasses import dataclass
from typing import List, Dict, Any
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from screen_capture import ScreenCapture
import json
import os
import imageio

@dataclass
class Source:
    id: str
    name: str
    type: str  # 'image', 'video', 'browser', 'camera', 'screen', 'window'
    properties: Dict[str, Any]
    visible: bool = True
    position: tuple = (0, 0)
    size: tuple = (1920, 1080)
    capture: ScreenCapture = None  # Новый атрибут для захвата
    last_frame: np.ndarray = None  # Кэш последнего удачного кадра

@dataclass
class Scene:
    id: str
    name: str
    sources: List[Source]
    active: bool = False

class SceneManager:
    def __init__(self):
        self.scenes: List[Scene] = []
        self.current_scene: Scene = None
        self.source_types = {
            'image': self._create_image_source,
            'video': self._create_video_source,
            'browser': self._create_browser_source,
            'camera': self._create_camera_source,
            'screen': self._create_screen_source,
            'window': self._create_window_source
        }
        self.config_path = 'config.json'
        self.load_config()

    def save_config(self):
        data = {
            'scenes': [
                {
                    'id': s.id,
                    'name': s.name,
                    'active': s.active,
                    'sources': [
                        {
                            'id': src.id,
                            'name': src.name,
                            'type': src.type,
                            'properties': src.properties,
                            'visible': src.visible,
                            'position': src.position,
                            'size': src.size
                        } for src in s.sources
                    ]
                } for s in self.scenes
            ],
            'current_scene_id': self.current_scene.id if self.current_scene else None
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_config(self):
        if not os.path.exists(self.config_path):
            return
        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.scenes = []
        for s in data.get('scenes', []):
            scene = Scene(
                id=s['id'],
                name=s['name'],
                sources=[],
                active=s.get('active', False)
            )
            for src in s['sources']:
                source = self.source_types[src['type']](src['name'], src['properties'])
                source.id = src['id']
                source.visible = src.get('visible', True)
                source.position = tuple(src.get('position', (0, 0)))
                source.size = tuple(src.get('size', (1920, 1080)))
                # Для screen/window сразу запускаем захват
                if src['type'] == 'screen':
                    source.capture = ScreenCapture()
                    source.capture.start_capture(region=None)
                elif src['type'] == 'window':
                    source.capture = ScreenCapture()
                    source.capture.start_capture(window_title=src['properties'].get('window_title'))
                scene.sources.append(source)
            self.scenes.append(scene)
        # Восстановить активную сцену
        cur_id = data.get('current_scene_id')
        for s in self.scenes:
            if s.id == cur_id:
                self.current_scene = s
                s.active = True
            else:
                s.active = False

    def create_scene(self, name: str) -> Scene:
        """
        Create a new scene
        :param name: Scene name
        :return: Created scene
        """
        scene = Scene(
            id=f"scene_{len(self.scenes)}",
            name=name,
            sources=[]
        )
        self.scenes.append(scene)
        return scene

    def delete_scene(self, scene_id: str):
        """
        Delete a scene
        :param scene_id: ID of the scene to delete
        """
        self.scenes = [s for s in self.scenes if s.id != scene_id]
        if self.current_scene and self.current_scene.id == scene_id:
            self.current_scene = None

    def set_active_scene(self, scene_id: str):
        """
        Set the active scene
        :param scene_id: ID of the scene to activate
        """
        for scene in self.scenes:
            if scene.id == scene_id:
                scene.active = True
                self.current_scene = scene
            else:
                scene.active = False

    def add_source(self, scene_id: str, source_type: str, name: str, properties: Dict[str, Any]) -> Source:
        """
        Add a source to a scene
        :param scene_id: ID of the scene to add the source to
        :param source_type: Type of source to create
        :param name: Name of the source
        :param properties: Properties for the source
        :return: Created source
        """
        if source_type not in self.source_types:
            raise ValueError(f"Unknown source type: {source_type}")

        source = self.source_types[source_type](name, properties)
        
        # Для screen/window создаём и запускаем захват
        if source_type == 'screen':
            source.capture = ScreenCapture()
            source.capture.start_capture(region=None)
        elif source_type == 'window':
            source.capture = ScreenCapture()
            source.capture.start_capture(window_title=properties.get('window_title'))
        
        for scene in self.scenes:
            if scene.id == scene_id:
                scene.sources.append(source)
                return source
        
        raise ValueError(f"Scene not found: {scene_id}")

    def remove_source(self, scene_id: str, source_id: str):
        """
        Remove a source from a scene
        :param scene_id: ID of the scene to remove the source from
        :param source_id: ID of the source to remove
        """
        for scene in self.scenes:
            if scene.id == scene_id:
                # Остановить захват, если есть
                for s in scene.sources:
                    if s.id == source_id and s.capture:
                        s.capture.stop_capture()
                scene.sources = [s for s in scene.sources if s.id != source_id]
                return
        raise ValueError(f"Scene not found: {scene_id}")

    def _create_image_source(self, name: str, properties: Dict[str, Any]) -> Source:
        """Create an image source"""
        return Source(
            id=f"image_{name}",
            name=name,
            type='image',
            properties=properties
        )

    def _create_video_source(self, name: str, properties: Dict[str, Any]) -> Source:
        """Create a video source"""
        return Source(
            id=f"video_{name}",
            name=name,
            type='video',
            properties=properties
        )

    def _create_browser_source(self, name: str, properties: Dict[str, Any]) -> Source:
        """Create a browser source"""
        return Source(
            id=f"browser_{name}",
            name=name,
            type='browser',
            properties=properties
        )

    def _create_camera_source(self, name: str, properties: Dict[str, Any]) -> Source:
        """Create a camera source"""
        return Source(
            id=f"camera_{name}",
            name=name,
            type='camera',
            properties=properties
        )

    def _create_screen_source(self, name: str, properties: Dict[str, Any]) -> Source:
        """Create a screen capture source"""
        return Source(
            id=f"screen_{name}",
            name=name,
            type='screen',
            properties=properties
        )

    def _create_window_source(self, name: str, properties: Dict[str, Any]) -> Source:
        return Source(
            id=f"window_{name}",
            name=name,
            type='window',
            properties=properties
        )

    def get_scene_preview(self, scene_id: str) -> np.ndarray:
        """
        Get a preview of the scene
        :param scene_id: ID of the scene to preview
        :return: numpy array containing the preview image
        """
        for scene in self.scenes:
            if scene.id == scene_id:
                preview_w, preview_h = 1920, 1080
                preview = np.zeros((preview_h, preview_w, 3), dtype=np.uint8)
                if not scene.sources:
                    return preview  # Нет источников — чёрный экран
                for source in scene.sources:
                    if not source.visible:
                        continue
                    frame = None
                    if source.type in ('screen', 'window') and source.capture:
                        frame = source.capture.get_frame()
                        if frame is not None:
                            source.last_frame = frame.copy()
                        else:
                            frame = source.last_frame
                    elif source.type == 'image':
                        try:
                            img = Image.open(source.properties['file']).convert('RGB')
                            frame = np.array(img)
                            source.last_frame = frame.copy()
                        except Exception:
                            frame = source.last_frame
                    elif source.type == 'video':
                        try:
                            if not hasattr(source, 'video_reader'):
                                source.video_reader = imageio.get_reader(source.properties['file'])
                                source.video_frame = 0
                            # Читаем следующий кадр
                            try:
                                frame = source.video_reader.get_data(source.video_frame)
                                source.last_frame = frame.copy()
                                source.video_frame += 1
                            except IndexError:
                                source.video_frame = 0
                                frame = source.video_reader.get_data(0)
                                source.last_frame = frame.copy()
                        except Exception:
                            frame = source.last_frame
                    elif source.type == 'browser':
                        # Заглушка для браузера
                        w, h = source.size
                        img = Image.new('RGB', (w, h), (40, 40, 60))
                        draw = ImageDraw.Draw(img)
                        url = source.properties.get('url', 'browser')
                        draw.text((10, h//2-10), f'Browser: {url}', fill=(200,200,200))
                        frame = np.array(img)
                        source.last_frame = frame.copy()
                    # --- Вставка кадра ---
                    if frame is not None:
                        src_h, src_w = frame.shape[:2]
                        dst_w, dst_h = source.size
                        scale = min(dst_w / src_w, dst_h / src_h)
                        new_w = int(src_w * scale)
                        new_h = int(src_h * scale)
                        frame_resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
                        x, y = source.position
                        ph, pw = preview.shape[:2]
                        offset_x = x + (dst_w - new_w) // 2
                        offset_y = y + (dst_h - new_h) // 2
                        if offset_y + new_h > ph:
                            new_h = ph - offset_y
                        if offset_x + new_w > pw:
                            new_w = pw - offset_x
                        if new_h > 0 and new_w > 0:
                            preview[offset_y:offset_y+new_h, offset_x:offset_x+new_w] = frame_resized[:new_h, :new_w]
                    else:
                        # Если нет ни одного кадра — рисуем заглушку
                        dst_w, dst_h = source.size
                        x, y = source.position
                        ph, pw = preview.shape[:2]
                        if y + dst_h > ph:
                            dst_h = ph - y
                        if x + dst_w > pw:
                            dst_w = pw - x
                        if dst_h > 0 and dst_w > 0:
                            img = Image.new('RGB', (dst_w, dst_h), (30, 30, 30))
                            draw = ImageDraw.Draw(img)
                            text = 'Источник недоступен'
                            draw.text((10, dst_h//2-10), text, fill=(200,200,200))
                            preview[y:y+dst_h, x:x+dst_w] = np.array(img)
                return preview
        
        raise ValueError(f"Scene not found: {scene_id}") 