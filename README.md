# Système de Gestion de Foule using YOLOv8

This project is a crowd management system for stadiums, using YOLOv8 for real-time detection of people and dangerous objects. It features a graphical interface (Tkinter) and saves frames when dangerous objects are detected.

## Prerequisites
- Python 3.8+
- [pip](https://pip.pypa.io/en/stable/)

## 1. Clone the Repository
```bash
git clone https://github.com/ANOUARELIDRISSI/Syst-me-de-Gestion-de-Foule-using-YoloV9.git
cd Syst-me-de-Gestion-de-Foule-using-YoloV9
```

## 2. Create and Activate a Virtual Environment
### On Windows
```bash
python -m venv env
.\env\Scripts\activate
```
### On macOS/Linux
```bash
python3 -m venv env
source env/bin/activate
```

## 3. Install Dependencies
```bash
pip install -r requirements.txt
```

## 4. Run the Project
```bash
python test.py
```

- The GUI will open. You can select a video file or use your camera.
- Detected dangerous objects will trigger alerts and save frames in the `dangerous_persons` folder.

## Notes
- Make sure you have a compatible GPU or CPU for running YOLOv8.
- The model file `yolov8n.pt` should be present in the project directory.

---
For any issues, please open an issue on the [GitHub repository](https://github.com/ANOUARELIDRISSI/Syst-me-de-Gestion-de-Foule-using-YoloV9). 