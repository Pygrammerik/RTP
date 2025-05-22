import cv2
import numpy as np
import pyautogui
from PIL import ImageGrab
import pygetwindow as gw
import win32gui
import win32con

class ScreenCapture:
    def __init__(self):
        self.is_capturing = False
        self.capture_region = None
        self.fps = 30
        self.window_title = None

    def start_capture(self, region=None, window_title=None):
        """
        Start capturing the screen or a window
        :param region: Tuple of (x, y, width, height) for region capture, None for full screen
        :param window_title: Title of the window to capture, None for screen
        """
        self.is_capturing = True
        self.capture_region = region
        self.window_title = window_title

    def stop_capture(self):
        """Stop capturing the screen"""
        self.is_capturing = False
        self.window_title = None

    def get_frame(self):
        """
        Get a single frame from the screen or window
        :return: numpy array containing the frame
        """
        if not self.is_capturing:
            return None

        if self.window_title:
            win = None
            for w in gw.getWindowsWithTitle(self.window_title):
                win = w
                break
            if win:
                if win.width == 0 or win.height == 0:
                    return None
                bbox = (win.left, win.top, win.right, win.bottom)
                try:
                    screenshot = ImageGrab.grab(bbox=bbox)
                except Exception:
                    return None
            else:
                return None
        elif self.capture_region:
            screenshot = ImageGrab.grab(bbox=self.capture_region)
        else:
            screenshot = ImageGrab.grab()

        frame = np.array(screenshot)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        return frame

    def get_available_windows(self):
        """
        Get list of available window titles
        :return: List of window titles
        """
        return [w.title for w in gw.getAllWindows() if w.title]

    def get_available_displays(self):
        """
        Get list of available displays
        :return: List of display information
        """
        displays = []
        for i in range(pyautogui.getActiveWindow()._getDisplayCount()):
            displays.append({
                'id': i,
                'name': f'Display {i+1}',
                'resolution': pyautogui.getActiveWindow()._getDisplayResolution(i)
            })
        return displays 