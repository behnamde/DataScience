from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import asyncio
from pydub import AudioSegment
import speech_recognition as sr
import uuid

app = FastAPI()

# Serve static files
app.mount("/static", StaticFiles(directory="transcribe/app/static"), name="static")

# Add CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Dictionary to store progress
progress_dict = {}

@app.get("/progress/{session_id}")
async def get_progress(session_id: str):
    return JSONResponse(content={"progress": progress_dict.get(session_id, 0)})

@app.get("/")
async def read_html():
    with open('transcribe/app/upload.html', 'r') as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.post("/transcribe/")
async def transcribe_upload(file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    session_id = uuid.uuid4().hex
    progress_dict[session_id] = 0

    file_ext = file.filename.split('.')[-1].lower()
    if file_ext not in SUPPORTED_FORMATS:
        return {"error": "Unsupported file format"}

    original_path = f"temp_{session_id}.{file_ext}"
    wav_path = f"temp_{session_id}.wav"
    txt_path = f"transcription_{session_id}.txt"

    with open(original_path, "wb") as buffer:
        buffer.write(await file.read())

    audio = AudioSegment.from_file(original_path, format=file_ext)
    audio.export(wav_path, format="wav")

    transcription = transcribe_audio_file(wav_path)

    with open(txt_path, "w") as text_file:
        text_file.write(transcription)

    background_tasks.add_task(os.remove, original_path)
    background_tasks.add_task(os.remove, wav_path)

    # Simulate progress
    for progress in range(10, 101, 10):
        progress_dict[session_id] = progress
        await asyncio.sleep(1)

    background_tasks.add_task(progress_dict.pop, session_id, None)

    return FileResponse(path=txt_path, filename="transcription.txt", media_type='text/plain', background=background_tasks)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)
