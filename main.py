import subprocess
import os
import json
import sys
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks
import httpx
import uvicorn
import logging
import re

logging.basicConfig(filename="app.log", level=logging.INFO)

# --- CONFIG ---
with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

PORT = config.get("port", 8000)
UPLOAD_URL = config.get("upload_url", "http://localhost:8000/upload")

app = FastAPI()

recording_process = None
current_output_file = None

# ✅ PyInstaller uchun ffmpeg path
def get_ffmpeg_path():
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "ffmpeg.exe")
    return os.path.join(os.getcwd(), "ffmpeg.exe")

FFMPEG_PATH = get_ffmpeg_path()


def get_default_mic():
    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        output = result.stderr.decode(errors="ignore")

        # faqat audio devices
        audio_mics = re.findall(r'"(.*?)"\s+\(audio\)', output)

        if audio_mics:
            logging.info(f"Avtomatik tanlangan mic: {audio_mics[0]}")
            return audio_mics[0]
        else:
            logging.error("Hech qanday audio microphone topilmadi")
            return None
    except Exception as e:
        logging.error(f"Mic tanlashda xato: {e}")
        return None


# --- UPLOAD ---
async def send_to_server(filepath: str):
    try:
        if not os.path.exists(filepath):
            logging.error("File topilmadi")
            return

        async with httpx.AsyncClient(timeout=None) as client:
            with open(filepath, "rb") as f:
                files = {
                    "file": (os.path.basename(filepath), f, "audio/mpeg")
                }
                response = await client.post(UPLOAD_URL, files=files)

        if response.status_code == 200:
            logging.info(f"Yuborildi: {filepath}")
            os.remove(filepath)
        else:
            logging.error(f"Server xato: {response.status_code} {response.text}")

    except Exception as e:
        logging.error(f"Upload xato: {e}")


# ▶ START
@app.post("/start")
def start_recording():
    global recording_process, current_output_file
    MIC_NAME = get_default_mic()

    if recording_process:
        return {"status": "already recording"}

    if not MIC_NAME:
        return {"status": "no microphone detected"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_output_file = f"record_{timestamp}.mp3"

    command = [
        FFMPEG_PATH,
        "-f", "dshow",
        "-i", f"audio={MIC_NAME}",
        "-ac", "1",
        "-ar", "44100",
        "-codec:a", "libmp3lame",
        "-b:a", "128k",
        "-y",
        current_output_file
    ]

    CREATE_NO_WINDOW = 0x08000000

    recording_process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.PIPE,   # 🔥 muhim
        creationflags=CREATE_NO_WINDOW
    )

    logging.info(f"Recording started: {current_output_file}")

    return {"status": "recording started", "filename": current_output_file}


# ⏹ STOP
@app.post("/stop")
def stop_recording(background_tasks: BackgroundTasks):
    global recording_process, current_output_file

    if not recording_process:
        return {"status": "not recording"}

    try:
        recording_process.stdin.write(b"q")
        recording_process.stdin.flush()
        recording_process.wait(timeout=5)
    except Exception as e:
        logging.error(f"Graceful stop ishlamadi: {e}")
        recording_process.kill()

    recording_process = None
    background_tasks.add_task(send_to_server, current_output_file)

    logging.info(f"Recording stopped: {current_output_file}")

    return {
        "status": "recording stopped",
        "file": current_output_file
    }


# 📊 STATUS
@app.get("/status")
def status():
    return {
        "recording": recording_process is not None,
        "current_file": current_output_file
    }


# 🔹 TEST MICS
@app.get("/mics")
def get_mics():
    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=0x08000000
        )
        output = result.stderr.decode(errors="ignore")
        return {"devices": output}
    except Exception as e:
        return {"error": str(e)}


# 🚀 RUN
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None)