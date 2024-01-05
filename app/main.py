from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi import File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os, datetime, asyncio, uuid, tempfile, logging
from pydub import AudioSegment
import speech_recognition as sr
from typing import Dict
import aiofiles, socketio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Create a Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI(title="Audio Transcription Service")
socket_app = socketio.ASGIApp(sio, app)

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

# Replace notify_task_update function with a Socket.IO version
async def notify_task_update(task_id, progress):
    logger.info(f"Current Tasks = {tasks.keys()}")
    timestamp = datetime.datetime.now()
    logger.info(f"Sending progress for taskId: {task_id} and progress: {progress} at {timestamp}")
    await sio.emit('progress_update', {"taskId": task_id, "progress": progress})

@sio.event
async def connect(sid, environ):
    logger.info(f"Socket connected: {sid}")

@sio.event
async def disconnect(sid):
    logger.info(f"Socket disconnected: {sid}")

@sio.event
async def cancel_task(sid, data):
    task_id = data['taskId']
    logger.info(f"Cancellation requested for task ID: {task_id}")
    if task_id in tasks:
        cancellation_flags[task_id] = True
        task = tasks[task_id]
        if not task.done():
            task.cancel()
        await sio.emit('message', {"message": f"Cancellation requested for task {task_id}"}, room=sid)
    else:
        await sio.emit('error', {"error": "Task not found"}, room=sid)

@app.post("/transcribe/")
async def transcribe_upload(request: Request,
                            file: UploadFile = File(...), 
                            background_tasks: BackgroundTasks = BackgroundTasks(),
                            language: str = Form(default="en-US")):
    task_id = uuid.uuid4().hex
    original_path = wav_path = txt_path = None

    try:
        file_ext = file.filename.split('.')[-1].lower()
        if file_ext not in SUPPORTED_FORMATS:
            return {"error": "Unsupported file format"}

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

        transcription = await transcription_task

        async with aiofiles.open(txt_path, mode="w") as text_file:
            await text_file.write(transcription)
            logger.info(f"Transcription written to file: {txt_path}")

    except asyncio.CancelledError:
        return JSONResponse(content={"taskId": task_id, "message": "Transcription cancelled"})
    
    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        return JSONResponse(content={"error": "An error occurred during processing"})

    finally:
        del tasks[task_id]
        cancellation_flags.pop(task_id, None)
        cleanup_files([original_path, wav_path], background_tasks, exclude=txt_path)
    
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

        progress = int((i + 1) / num_chunks * 100)
        await notify_task_update(task_id, progress)

    return full_text

def make_chunks(audio_segment, chunk_length_ms):
    return [audio_segment[i:i + chunk_length_ms] for i in range(0, len(audio_segment), chunk_length_ms)]

@app.get("/")
async def read_html(request: Request):
    return templates.TemplateResponse("index_test.html", {"request": request})

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
    uvicorn.run(socket_app, host="localhost", port=8000)
