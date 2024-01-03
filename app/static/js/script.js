document.addEventListener("DOMContentLoaded", function() {
    const elements = {
        uploadForm: document.getElementById('upload-form'),
        loadingAnimation: document.getElementById('loading'),
        progressBarContainer: document.getElementById('progress-container'),
        progressBar: document.getElementById('progress-bar'),
        statusMessage: document.getElementById('status-message'),
        transcriptionTextArea: document.getElementById('transcription-text'),
        transcriptionResultContainer: document.getElementById('transcription-result'),
        downloadButton: document.getElementById('download-btn'),
        cancelButton: document.getElementById('cancel-btn'),
        repeatButton: document.getElementById('repeat-btn'),
        fileUploadInput: document.getElementById('file-upload'),
        dragDropArea: document.getElementById('drag-drop-area'),
        fileNameDisplay: document.getElementById('file-name')
    };

    let downloadUrl = null;
    let progressInterval;
    let taskId = null;

    const supportedLanguages = {
        'en': 'en-US',
        'sp': 'es-ES',
        'pt': 'pt-PT'
        // Additional languages can be added here
    };

    function updateFileName() {
        if (elements.fileUploadInput.files.length > 0) {
            elements.fileNameDisplay.textContent = `Selected file: ${elements.fileUploadInput.files[0].name}`;
        }
    }

    elements.fileUploadInput.addEventListener('change', updateFileName);

    elements.dragDropArea.addEventListener('click', () => elements.fileUploadInput.click());

    elements.dragDropArea.addEventListener('dragover', (event) => {
        event.preventDefault();
        elements.dragDropArea.classList.add('drag-drop-active');
    });

    elements.dragDropArea.addEventListener('dragleave', () => {
        elements.dragDropArea.classList.remove('drag-drop-active');
    });

    elements.dragDropArea.addEventListener('drop', (event) => {
        event.preventDefault();
        elements.dragDropArea.classList.remove('drag-drop-active');
        if (event.dataTransfer.files.length) {
            elements.fileUploadInput.files = event.dataTransfer.files;
            updateFileName();
        }
    });

    function resetUI() {
        elements.progressBarContainer.style.display = 'none';
        elements.loadingAnimation.style.display = 'none';
        elements.statusMessage.textContent = '';
        elements.downloadButton.style.display = 'none';
        elements.cancelButton.style.display = 'none';
        elements.repeatButton.style.display = 'none';
        elements.transcriptionResultContainer.style.display = 'none';
        elements.uploadForm.reset();
        elements.fileNameDisplay.textContent = '';
        const submitButton = elements.uploadForm.querySelector('input[type="submit"]');
        if (submitButton) {
            submitButton.disabled = false;
        }
        taskId = null;
    }

    function updateProgress(step) {
        const progressPercentages = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100];
        elements.progressBar.style.width = `${progressPercentages[step]}%`;
    }

    function simulateProgress() {
        let step = 0;
        progressInterval = setInterval(() => {
            if (step < progressPercentages.length - 1) {
                updateProgress(step++);
            } else {
                clearInterval(progressInterval);
                updateProgress(step); // Ensure it reaches 100%
            }
        }, 500); // Adjust time as needed
    }

    // Establish WebSocket connection
    const socket = new WebSocket(`ws://${location.host}/ws`);
    socket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.task_id) {
            taskId = data.task_id;
            console.log(`Received task ID update: ${taskId}`);
            // Update the UI based on the received task ID
            elements.statusMessage.textContent = `Processing task ID: ${taskId}`;
        }
    };

    socket.onerror = function(error) {
        console.error('WebSocket error:', error);
    };

    socket.onclose = function() {
        console.log('WebSocket connection closed');
    };

    elements.cancelButton.addEventListener('click', function() {
        if (taskId) {
            // Immediately stop progress and update UI
            clearInterval(progressInterval);
            elements.progressBar.style.width = '0%';
            elements.loadingAnimation.style.display = 'none';
            elements.statusMessage.textContent = 'Cancelling transcription...';
            elements.cancelButton.style.display = 'none';
    
            // Send cancellation request to the server
            fetch(`/cancel/${taskId}`, { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    console.log('Cancellation response:', data);
                    elements.statusMessage.textContent = 'Transcription cancelled.';
                    taskId = null;
                    resetUI();
                })
                .catch(error => {
                    console.error('Error:', error);
                    elements.statusMessage.textContent = 'Error cancelling transcription.';
                });
        } else {
            console.error('No transcription task to cancel.');
            elements.statusMessage.textContent = 'No ongoing transcription task found.';
        }
    });
    

    elements.repeatButton.addEventListener('click', resetUI);

    elements.uploadForm.addEventListener('submit', function(event) {
        event.preventDefault();
        const selectedLanguage = document.getElementById('language-select').value;
        const languageCode = supportedLanguages[selectedLanguage];

        elements.loadingAnimation.style.display = 'block';
        elements.progressBarContainer.style.display = 'block';
        elements.progressBar.style.width = '0%';
        elements.statusMessage.textContent = 'Uploading, please wait...';
        elements.cancelButton.style.display = 'block';

        simulateProgress();

        const formData = new FormData(elements.uploadForm);
        formData.append('language', languageCode);

        fetch('/transcribe/', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            return response.json();
        })
        .then(data => {
            clearInterval(progressInterval);
            updateProgress(19);
            elements.loadingAnimation.style.display = 'none';                    
            elements.statusMessage.textContent = 'Transcription complete. You can review and download your file.';
            elements.transcriptionTextArea.value = data.transcription;
            elements.transcriptionResultContainer.style.display = 'block';
            downloadUrl = data.downloadUrl;
            elements.downloadButton.style.display = 'block';
            elements.cancelButton.style.display = 'none';
            elements.repeatButton.style.display = 'block';
            taskId = data.taskId;
        })
        .catch(error => {
            elements.loadingAnimation.style.display = 'none';
            console.error('Error:', error);
            elements.statusMessage.textContent = 'An error occurred.';
            resetUI();
        });
    });

    elements.downloadButton.addEventListener('click', function() {
        if (downloadUrl) {
            window.open(downloadUrl, '_blank');
            elements.statusMessage.textContent = 'Your file is being downloaded.';
            resetUI();
        } else {
            elements.statusMessage.textContent = 'No file available for download.';
        }
    });
});
