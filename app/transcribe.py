from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Request, HTTPException, WebSocket, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
from pydub import AudioSegment
import speech_recognition as sr
import uuid
import asyncio
from functools import wraps
from typing import Any, Awaitable, Callable

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
active_connections = []

async def notify_task_update(task_id):
    closed_connections = []
    for connection in active_connections:
        if not connection.client_state == WebSocketState.CONNECTED:
            closed_connections.append(connection)
            continue
        await connection.send_json({"task_id": task_id})
    for conn in closed_connections:
        active_connections.remove(conn)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        print(e)
    finally:
        active_connections.remove(websocket)

async def disconnect_poller(request: Request, result: Any):
    try:
        while not await request.is_disconnected():
            await asyncio.sleep(0.01)
        print("Request disconnected")
        return result
    except asyncio.CancelledError:
        print("Stopping polling loop")

def cancel_on_disconnect(handler: Callable[[Request], Awaitable[Any]]):
    @wraps(handler)
    async def cancel_on_disconnect_decorator(request: Request, *args, **kwargs):
        sentinel = object()
        poller_task = asyncio.ensure_future(disconnect_poller(request, sentinel))
        handler_task = asyncio.ensure_future(handler(request, *args, **kwargs))

        done, pending = await asyncio.wait(
            [poller_task, handler_task], return_when=asyncio.FIRST_COMPLETED
        )

        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                print(f"{t} was cancelled")
            except Exception as exc:
                print(f"{t} raised {exc} when being cancelled")

        if handler_task in done:
            return await handler_task

        raise HTTPException(503)

    return cancel_on_disconnect_decorator

@app.post("/transcribe/")
@cancel_on_disconnect
async def transcribe_upload(request: Request,
                            file: UploadFile = File(...), 
                            background_tasks: BackgroundTasks = BackgroundTasks(),
                            language: str = Form(default="en-US")):
    file_ext = file.filename.split('.')[-1].lower()
    if file_ext not in SUPPORTED_FORMATS:
        return {"error": "Unsupported file format"}

    task_id = uuid.uuid4().hex
    original_path = f"temp_{task_id}.{file_ext}"
    wav_path = f"temp_{task_id}.wav"
    txt_path = f"transcription_{task_id}.txt"

    with open(original_path, "wb") as buffer:
        buffer.write(await file.read())

    audio = AudioSegment.from_file(original_path, format=file_ext)
    audio.export(wav_path, format="wav")

    transcription_task = asyncio.create_task(transcribe_audio_file(wav_path,
                                                                   task_id, 
                                                                   language=language))
    tasks[task_id] = transcription_task

    # Notify clients about the task_id update
    await notify_task_update(task_id)

    try:
        transcription = await transcription_task
    except asyncio.CancelledError:
        return JSONResponse(content={"taskId": task_id, 
                                     "message": "Transcription cancelled"})
    finally:
        del tasks[task_id]
        cleanup_files([original_path, wav_path, txt_path], background_tasks)

    with open(txt_path, "w") as text_file:
        text_file.write(transcription)

    return JSONResponse(content={"taskId": task_id, 
                                 "downloadUrl": f"/download/{task_id}",
                                 "transcription": transcription})

@app.get("/download/{task_id}")
async def download_transcription(task_id: str, background_tasks: BackgroundTasks):
    txt_path = f"transcription_{task_id}.txt"
    if os.path.exists(txt_path):
        response = FileResponseWithCleanup(path=txt_path, 
                                           filename="transcription.txt", 
                                           media_type='text/plain', 
                                           background_tasks=background_tasks)
        return response
    else:
        raise HTTPException(status_code=404, detail="File not found")

@app.post("/cancel/{task_id}")
async def cancel_task(task_id: str):
    if task_id in tasks:
        tasks[task_id].cancel()
        return {"message": f"Task {task_id} cancelled"}
    raise HTTPException(status_code=404, detail="Task not found")

async def transcribe_audio_file(wav_path, task_id, language="en-US", chunk_length_ms=59000):
    audio = AudioSegment.from_wav(wav_path)
    chunks = make_chunks(audio, chunk_length_ms)
    full_text = ""

    for i, chunk in enumerate(chunks):
        if task_id in tasks and tasks[task_id].cancelled():
            return "[Cancelled]"

        chunk_name = f"chunk_{uuid.uuid4().hex}.wav"
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
            
        os.remove(chunk_name)

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
            print(f"Error deleting file {path}: {e}")

def cleanup_files(file_paths, background_tasks):
    for path in file_paths:
        background_tasks.add_task(os.remove, path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)

