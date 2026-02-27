import subprocess
import os
import signal
import json
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks
import httpx
import uvicorn
import asyncio
import logging

logging.basicConfig(filename="app.log", level=logging.INFO)


with open("config.json", encoding="utf-8") as f:
    config = json.load(f)

MIC_NAME = config["mic_name"]
PORT = config["port"]
UPLOAD_URL = config["upload_url"]

app = FastAPI()

recording_process = None
current_output_file = None
FFMPEG_PATH = os.path.join(os.getcwd(), "ffmpeg.exe")


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


@app.post("/start")
def start_recording():
    global recording_process, current_output_file

    if recording_process:
        return {"status": "already recording"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_output_file = f"record_{timestamp}.wav"

    command = [
        FFMPEG_PATH,
        "-f", "dshow",
        "-i", f"audio={MIC_NAME}",
        "-ac", "1",
        "-ar", "44100",
        "-y",
        current_output_file
    ]

    CREATE_NO_WINDOW = 0x08000000
    CREATE_NEW_PROCESS_GROUP = 0x00000200

    recording_process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    )

    logging.info(f"Recording started: {current_output_file}")

    return {"status": "recording started", "filename": current_output_file}


# ⏹ STOP RECORDING
@app.post("/stop")
def stop_recording(background_tasks: BackgroundTasks):
    global recording_process, current_output_file

    if not recording_process:
        return {"status": "not recording"}

    try:
        recording_process.send_signal(signal.CTRL_BREAK_EVENT)
        recording_process.wait(timeout=5)
    except Exception as e:
        logging.error(f"Graceful stop ishlamadi: {e}")
        recording_process.kill()

    recording_process = None

    # Telegramga yuborishni fon rejimda boshlaymiz
    background_tasks.add_task(send_to_server, current_output_file)

    logging.info(f"Recording stopped: {current_output_file}")

    return {
        "status": "recording stopped",
        "file": current_output_file
    }

@app.get("/status")
def status():
    return {
        "recording": recording_process is not None,
        "current_file": current_output_file
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None)
