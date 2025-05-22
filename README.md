# RTP - Record Tool Python

RTP (Record Tool Python) — это клон OBS, написанный на Python, для записи, стриминга и управления сценами/источниками.

## Features

- Screen, window, image, video, browser sources
- Scene management, layers, visibility
- Drag & resize sources in preview
- Audio mixer with VU-meter (Mic/Aux)
- Recording to mp4, screenshots
- Profile export/import
- Scene transitions (cut/fade)
- Modern PyQt6-based UI

## Requirements

- Python 3.8+
- PyQt6
- OpenCV
- NumPy
- PyAutoGUI
- SoundDevice
- SoundFile
- Pillow
- ffmpeg-python
- imageio
- pygetwindow
- pywin32

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/rtp.git
cd rtp
```
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:
```bash
python main.py
```
2. Add scenes and sources, manage layers, record or stream!

## License
MIT 