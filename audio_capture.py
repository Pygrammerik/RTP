import sounddevice as sd
import soundfile as sf
import numpy as np
import queue
import threading

class AudioCapture:
    def __init__(self):
        self.is_capturing = False
        self.sample_rate = 44100
        self.channels = 2
        self.audio_queue = queue.Queue()
        self.recording_thread = None
        self.audio_data = []

    def start_capture(self):
        """Start capturing audio"""
        if not self.is_capturing:
            self.is_capturing = True
            self.audio_data = []
            self.recording_thread = threading.Thread(target=self._capture_audio)
            self.recording_thread.start()

    def stop_capture(self):
        """Stop capturing audio"""
        self.is_capturing = False
        if self.recording_thread:
            self.recording_thread.join()

    def _capture_audio(self):
        """Internal method to capture audio"""
        def callback(indata, frames, time, status):
            if status:
                print(status)
            if self.is_capturing:
                self.audio_data.append(indata.copy())

        with sd.InputStream(samplerate=self.sample_rate,
                          channels=self.channels,
                          callback=callback):
            while self.is_capturing:
                sd.sleep(100)

    def save_audio(self, filename):
        """
        Save captured audio to file
        :param filename: Output filename
        """
        if self.audio_data:
            audio_data = np.concatenate(self.audio_data, axis=0)
            sf.write(filename, audio_data, self.sample_rate)

    def get_available_devices(self):
        """
        Get list of available audio devices
        :return: List of audio device information
        """
        devices = sd.query_devices()
        return [{
            'id': i,
            'name': device['name'],
            'channels': device['max_input_channels'],
            'sample_rate': device['default_samplerate']
        } for i, device in enumerate(devices) if device['max_input_channels'] > 0] 