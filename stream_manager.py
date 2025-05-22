import cv2
import numpy as np
import threading
import queue
import time
import subprocess
import ffmpeg

class StreamManager:
    def __init__(self):
        self.is_streaming = False
        self.stream_thread = None
        self.frame_queue = queue.Queue(maxsize=30)
        self.audio_queue = queue.Queue(maxsize=30)
        self.ffmpeg_process = None
        self.stream_url = None
        self.stream_key = None

    def start_stream(self, stream_url, stream_key):
        """
        Start streaming to the specified RTMP URL
        :param stream_url: RTMP server URL
        :param stream_key: Stream key for authentication
        """
        if not self.is_streaming:
            self.stream_url = stream_url
            self.stream_key = stream_key
            self.is_streaming = True
            self.stream_thread = threading.Thread(target=self._stream_worker)
            self.stream_thread.start()

    def stop_stream(self):
        """Stop the current stream"""
        self.is_streaming = False
        if self.stream_thread:
            self.stream_thread.join()
        if self.ffmpeg_process:
            self.ffmpeg_process.terminate()
            self.ffmpeg_process = None

    def add_frame(self, frame):
        """
        Add a video frame to the stream queue
        :param frame: numpy array containing the frame
        """
        if self.is_streaming and not self.frame_queue.full():
            self.frame_queue.put(frame)

    def add_audio(self, audio_data):
        """
        Add audio data to the stream queue
        :param audio_data: numpy array containing audio samples
        """
        if self.is_streaming and not self.audio_queue.full():
            self.audio_queue.put(audio_data)

    def _stream_worker(self):
        """Internal method to handle streaming"""
        try:
            # Configure FFmpeg command
            command = [
                'ffmpeg',
                '-f', 'rawvideo',
                '-pix_fmt', 'bgr24',
                '-s', '1920x1080',  # Adjust based on your capture resolution
                '-r', '30',
                '-i', 'pipe:0',
                '-f', 'f32le',
                '-ar', '44100',
                '-ac', '2',
                '-i', 'pipe:1',
                '-c:v', 'libx264',
                '-preset', 'veryfast',
                '-b:v', '3000k',
                '-maxrate', '3000k',
                '-bufsize', '6000k',
                '-pix_fmt', 'yuv420p',
                '-g', '50',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ar', '44100',
                '-f', 'flv',
                f'{self.stream_url}/{self.stream_key}'
            ]

            # Start FFmpeg process
            self.ffmpeg_process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            while self.is_streaming:
                # Get frame from queue
                if not self.frame_queue.empty():
                    frame = self.frame_queue.get()
                    self.ffmpeg_process.stdin.write(frame.tobytes())

                # Get audio from queue
                if not self.audio_queue.empty():
                    audio_data = self.audio_queue.get()
                    self.ffmpeg_process.stdin.write(audio_data.tobytes())

                time.sleep(1/30)  # Maintain 30 FPS

        except Exception as e:
            print(f"Streaming error: {str(e)}")
            self.stop_stream()

    def get_stream_status(self):
        """
        Get current streaming status
        :return: Dictionary containing streaming status information
        """
        return {
            'is_streaming': self.is_streaming,
            'queue_size': self.frame_queue.qsize(),
            'stream_url': self.stream_url
        } 