# Audio Transcription Service

## Overview

This application is a web-based service for transcribing audio files. It is built using FastAPI and handles audio file uploads, transcribes them into text, and allows users to download the transcribed text. The service supports various audio formats and efficiently handles larger files by processing them in chunks.

## Features

- File upload for audio transcription.
- Support for multiple audio formats (MP3, WAV, M4A).
- Chunk-based processing for handling large audio files.
- Asynchronous background processing.
- Real-time progress tracking.
- Downloadable transcription results.

## Installation

### Prerequisites

- Python 3.6 or higher
- FastAPI
- Uvicorn (ASGI server)
- Pydub
- SpeechRecognition
- aiofiles

### Setup

1. **Clone the Repository:**
   ```
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Install Dependencies:**
   ```
   pip install fastapi uvicorn pydub SpeechRecognition aiofiles
   ```

3. **Running the Server:**
   ```
   uvicorn main:app --reload
   ```
   The server will start and be available at `http://localhost:8000`.

## Usage

- Navigate to `http://localhost:8000` in your web browser to access the audio transcription service.
- Upload an audio file using the provided form.
- Monitor the progress of the transcription.
- Once complete, review the transcription text and download it if needed.
- The service also provides endpoints for checking the progress (`/progress/{session_id}`) and downloading the transcription (`/download/{session_id}`).

## Project Structure

- `main.py`: Main FastAPI application setup and route definitions.
- `audio_transcriber.py`: Module containing the logic for audio transcription.
- `static/`: Directory for static files like CSS and JavaScript.
- `templates/`: Directory for HTML templates.

## Notes

- Ensure that FFmpeg is installed and accessible in your system's PATH if dealing with various audio formats.
- For production deployment, consider using a more secure CORS configuration and ensure proper error handling and logging.
- The transcription accuracy depends on the quality of the audio input and the capabilities of the SpeechRecognition library.
