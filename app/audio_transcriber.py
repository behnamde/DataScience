from pydub import AudioSegment
import speech_recognition as sr
import os
import asyncio
import logging

# Supported audio formats
SUPPORTED_FORMATS = ["mp3", "wav", "m4a"]

async def transcribe_audio(original_path, wav_path, file_ext, session_id, progress_dict):
    try:
        audio = AudioSegment.from_file(original_path, format=file_ext)
        audio.export(wav_path, format="wav")

        chunk_length_ms = 30000
        chunks = make_chunks(audio, chunk_length_ms)

        full_text = ""
        recognizer = sr.Recognizer()

        for i, chunk in enumerate(chunks):
            chunk_name = f"chunk_{i}_{session_id}.wav"
            chunk.export(chunk_name, format="wav")

            with sr.AudioFile(chunk_name) as source:
                audio_data = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio_data)
                    full_text += text + " "
                except sr.UnknownValueError:
                    full_text += "[Unintelligible] "
                except sr.RequestError as e:
                    full_text += "[Error] "

            progress_dict[session_id] = int((i + 1) / len(chunks) * 100)
            await asyncio.sleep(0.1)

            os.remove(chunk_name)

        return full_text

    except Exception as e:
        logging.error(f"Error in transcribing audio: {e}")
        return "[Transcription Failed]"

def make_chunks(audio_segment, chunk_length_ms):
    return [audio_segment[i:i + chunk_length_ms] for i in range(0, len(audio_segment), chunk_length_ms)]
