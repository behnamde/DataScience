from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
from pydub import AudioSegment
import speech_recognition as sr
import uuid
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

app = FastAPI()

# Add CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Supported audio formats
SUPPORTED_FORMATS = ["mp3", "wav", "m4a"]

def transcribe_audio_file(wav_path, chunk_length_ms=59000):
    audio = AudioSegment.from_wav(wav_path)
    chunks = make_chunks(audio, chunk_length_ms)
    full_text = ""

    for i, chunk in enumerate(chunks):
        chunk_name = f"chunk_{uuid.uuid4().hex}.wav"
        chunk.export(chunk_name, format="wav")

        recognizer = sr.Recognizer()
        with sr.AudioFile(chunk_name) as source:
            audio_data = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio_data)
                full_text += text + " "
            except sr.UnknownValueError:
                full_text += "[Unintelligible] "
            except sr.RequestError as e:
                full_text += "[Error] "
        
        # Ensure the file is closed before deleting
        try:
            os.remove(chunk_name)
        except Exception as e:
            print(f"Error deleting file {chunk_name}: {e}")

    return full_text

def make_chunks(audio_segment, chunk_length_ms):
    """Breaks an AudioSegment into chunks of a specified length."""
    return [audio_segment[i:i + chunk_length_ms] for i in range(0, len(audio_segment), chunk_length_ms)]

@app.get("/")
async def read_html(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@app.post("/transcribe/")
async def transcribe_upload(file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    file_ext = file.filename.split('.')[-1].lower()
    if file_ext not in SUPPORTED_FORMATS:
        return {"error": "Unsupported file format"}

    unique_id = uuid.uuid4().hex
    original_path = f"temp_{unique_id}.{file_ext}"
    wav_path = f"temp_{unique_id}.wav"
    txt_path = f"transcription_{unique_id}.txt"

    with open(original_path, "wb") as buffer:
        buffer.write(await file.read())

    audio = AudioSegment.from_file(original_path, format=file_ext)
    audio.export(wav_path, format="wav")

    transcription = transcribe_audio_file(wav_path)

    with open(txt_path, "w") as text_file:
        text_file.write(transcription)

    background_tasks.add_task(os.remove, original_path)
    background_tasks.add_task(os.remove, wav_path)

    return FileResponse(path=txt_path, filename="transcription.txt", media_type='text/plain', background=background_tasks)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)