from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi import WebSocket, WebSocketDisconnect
from fastapi import File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import tempfile
from pydub import AudioSegment
import speech_recognition as sr
import uuid
import asyncio
from functools import wraps
from typing import Any, Awaitable, Callable, Dict
import logging
import aiofiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Audio Transcription Service")

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPPORTED_FORMATS = ["mp3", "wav", "m4a"]
tasks = {}
cancellation_flags: Dict[str, bool] = {}
active_connections = []

async def notify_task_update(task_id, progress):
    disconnected_connections = []
    for connection in active_connections:
        if connection.application_state != "connected":
            disconnected_connections.append(connection)
            continue
        try:
            await connection.send_json({"task_id": task_id, "progress": progress})
        except WebSocketDisconnect:
            disconnected_connections.append(connection)

    for conn in disconnected_connections:
        active_connections.remove(conn)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        active_connections.remove(websocket)

@app.post("/transcribe/")
async def transcribe_upload(request: Request,
                            file: UploadFile = File(...), 
                            background_tasks: BackgroundTasks = BackgroundTasks(),
                            language: str = Form(default="en-US")):
    file_ext = file.filename.split('.')[-1].lower()
    if file_ext not in SUPPORTED_FORMATS:
        return {"error": "Unsupported file format"}

    task_id = uuid.uuid4().hex

    async with aiofiles.tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as temp_file:
        content = await file.read()
        await temp_file.write(content)
        original_path = temp_file.name

    wav_path = f"{tempfile.gettempdir()}/temp_{task_id}.wav"
    txt_path = f"{tempfile.gettempdir()}/transcription_{task_id}.txt"

    audio = AudioSegment.from_file(original_path, format=file_ext)
    audio.export(wav_path, format="wav")

    cancellation_flags[task_id] = False
    transcription_task = asyncio.create_task(transcribe_audio_file(wav_path, task_id, language=language))
    logger.info(f"Task created with ID: {task_id}")
    tasks[task_id] = transcription_task
    await notify_task_update(task_id, 0)  # Initial progress update

    try:
        transcription = await transcription_task
    except asyncio.CancelledError:
        return JSONResponse(content={"taskId": task_id, "message": "Transcription cancelled"})
    finally:
        del tasks[task_id]
        cancellation_flags.pop(task_id, None)
        cleanup_files([original_path, wav_path, txt_path], background_tasks)

    async with aiofiles.open(txt_path, mode="w") as text_file:
        await text_file.write(transcription)

    return JSONResponse(content={"taskId": task_id, "downloadUrl": f"/download/{task_id}", "transcription": transcription})

@app.get("/download/{task_id}")
async def download_transcription(task_id: str, background_tasks: BackgroundTasks):
    txt_path = f"{tempfile.gettempdir()}/transcription_{task_id}.txt"
    if os.path.exists(txt_path):
        response = FileResponseWithCleanup(path=txt_path, filename="transcription.txt", media_type='text/plain', background_tasks=background_tasks)
        return response
    else:
        raise HTTPException(status_code=404, detail="File not found")

@app.post("/cancel/{task_id}")
async def cancel_task(task_id: str):
    logger.info(f"Cancellation requested for task ID: {task_id}")
    logger.info(f"Current tasks: {list(tasks.keys())}")
    if task_id in tasks:
        cancellation_flags[task_id] = True
        task = tasks[task_id]
        if not task.done():
            task.cancel()
        return {"message": f"Cancellation requested for task {task_id}"}
    raise HTTPException(status_code=404, detail="Task not found")

async def transcribe_audio_file(wav_path, task_id, language="en-US", chunk_length_ms=59000):
    audio = AudioSegment.from_wav(wav_path)
    chunks = make_chunks(audio, chunk_length_ms)
    num_chunks = len(chunks)
    full_text = ""

    for i, chunk in enumerate(chunks):
        if cancellation_flags.get(task_id, False):
            logger.info(f"Task {task_id} cancelled, stopping transcription.")
            raise asyncio.CancelledError

        async with aiofiles.tempfile.NamedTemporaryFile(delete=True, suffix=".wav") as temp_chunk_file:
            chunk_name = temp_chunk_file.name
            chunk.export(chunk_name, format="wav")

            recognizer = sr.Recognizer()
            with sr.AudioFile(chunk_name) as source:
                audio_data = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio_data, language=language)
                    full_text += text + " "
                except sr.UnknownValueError:
                    full_text += "[Unintelligible] "
                except sr.RequestError as e:
                    full_text += "[Error] "
        
        progress = (i + 1) / num_chunks * 100
        await notify_task_update(task_id, progress)

    return full_text

def make_chunks(audio_segment, chunk_length_ms):
    return [audio_segment[i:i + chunk_length_ms] for i in range(0, len(audio_segment), chunk_length_ms)]

@app.get("/")
async def read_html(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/loading_clock_2.gif")
async def get_loading_gif():
    return FileResponse("templates/loading_clock_2.gif")

@app.get("/favicon.ico")
async def get_favicon():
    return FileResponse("templates/favicon.ico")

class FileResponseWithCleanup(FileResponse):
    def __init__(self, path: str, background_tasks: BackgroundTasks, *args, **kwargs):
        super().__init__(path, *args, **kwargs)
        background_tasks.add_task(self.delete_file, path=path)

    async def delete_file(self, path):
        try:
            os.remove(path)
        except Exception as e:
            logger.error(f"Error deleting file {path}: {e}")

def cleanup_files(file_paths, background_tasks):
    for path in file_paths:
        background_tasks.add_task(os.remove, path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
