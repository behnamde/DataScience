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
from typing import Dict
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
    logger.info(f"Current Tasks = {tasks.keys()}")
    disconnected_connections = []
    for connection in active_connections:
        try:
            logger.info(f"Checking connection state for taskId: {task_id} and progress: {progress}")
            await connection.send_json({"taskId": task_id, "progress": progress})
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for taskId: {task_id}. Removing connection.")
            disconnected_connections.append(connection)
            continue

    for conn in disconnected_connections:
        active_connections.remove(conn)
        logger.info(f"Connection removed for taskId: {task_id}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if "cancelTask" in data and "taskId" in data:
                task_id = data["taskId"]
                await cancel_task(task_id, websocket)
    except WebSocketDisconnect:
        active_connections.remove(websocket)

async def cancel_task(task_id, websocket):
    logger.info(f"Cancellation requested for task ID: {task_id}")
    if task_id in tasks:
        cancellation_flags[task_id] = True
        task = tasks[task_id]
        if not task.done():
            task.cancel()
        await websocket.send_json({"message": f"Cancellation requested for task {task_id}"})
    else:
        await websocket.send_json({"error": "Task not found"})

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

    wav_path = f"{tempfile.gettempdir()}\\temp_{task_id}.wav"
    txt_path = f"{tempfile.gettempdir()}\\transcription_{task_id}.txt"

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
        # del tasks[task_id]
        cancellation_flags.pop(task_id, None)
        # Exclude the transcription file from immediate cleanup
        cleanup_files([original_path, wav_path], background_tasks, exclude=txt_path)


    async with aiofiles.open(txt_path, mode="w") as text_file:
        try:
            await text_file.write(transcription)
            logger.info(f"Transcription written to file: {txt_path}")
        except Exception as e:
            logger.error(f"Error writing transcription to file: {e}")


    return JSONResponse(content={"taskId": task_id, "downloadUrl": f"/download/{task_id}", "transcription": transcription})

@app.get("/download/{task_id}")
async def download_transcription(task_id: str, background_tasks: BackgroundTasks):
    txt_path = f"{tempfile.gettempdir()}\\transcription_{task_id}.txt"
    logger.info(f"Attempting to download file at: {txt_path}")  # Log the file path

    if os.path.exists(txt_path):
        logger.info(f"File found, preparing download for: {txt_path}")
        response = FileResponseWithCleanup(path=txt_path, filename="transcription.txt", media_type='text/plain', background_tasks=background_tasks)
        return response
    else:
        logger.error(f"File not found at: {txt_path}")
        raise HTTPException(status_code=404, detail="File not found")

async def transcribe_audio_file(wav_path, task_id, language="en-US", chunk_length_ms=10000):
    audio = AudioSegment.from_wav(wav_path)
    chunks = make_chunks(audio, chunk_length_ms)
    num_chunks = len(chunks)
    full_text = ""

    for i, chunk in enumerate(chunks):
        if cancellation_flags.get(task_id, False):
            logger.info(f"Task {task_id} cancelled, stopping transcription.")
            raise asyncio.CancelledError

        # Create a temporary file name
        _, temp_chunk_file = tempfile.mkstemp(suffix=".wav")
        try:
            chunk.export(temp_chunk_file, format="wav")

            recognizer = sr.Recognizer()
            with sr.AudioFile(temp_chunk_file) as source:
                audio_data = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio_data, language=language)
                    full_text += text + " "
                except sr.UnknownValueError:
                    full_text += "[Unintelligible] "
                except sr.RequestError as e:
                    full_text += "[Error] "
        finally:
            # Close the file if it's open in another context
            try:
                os.close(_)
            except OSError as e:
                logger.error(f"Error closing file handle: {e}")
            # Ensure the temporary file is deleted
            try:
                os.remove(temp_chunk_file)
            except OSError as e:
                logger.error(f"Error removing temporary file: {e}")

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
        await asyncio.sleep(10)
        try:
            os.remove(path)
        except Exception as e:
            logger.error(f"Error deleting file {path}: {e}")

def cleanup_files(file_paths, background_tasks, exclude=None):
    if exclude is not None:
        file_paths = [path for path in file_paths if path != exclude]
    for path in file_paths:
        background_tasks.add_task(os.remove, path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
