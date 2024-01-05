document.addEventListener("DOMContentLoaded", function() {
    let socket;
    let downloadUrl = null;
    let taskId = null;

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

    function connectWebSocket() {
        const socketProtocol = (window.location.protocol === 'https:') ? 'wss:' : 'ws:';
        const socket = new WebSocket(`${socketProtocol}//${location.host}/ws`);
    
        socket.onopen = function() {
            console.log("WebSocket connection established");
        };
    
        socket.onmessage = function(event) {
            let timestamp = new Date();
            const data = JSON.parse(event.data);
            console.log("WebSocket message received:", data);
            console.log("time =", timestamp)
        
            // Check if the message contains taskId and progress
            if (data.taskId && data.hasOwnProperty('progress')) {
                taskId = data.taskId;
                updateProgress(taskId, data.progress);
                elements.statusMessage.textContent = `Processing Percentage: ${data.progress}%`;
            } 
            // Handle cancellation message
            else if (data.message && data.message.includes('Cancellation requested')) {
                console.log(data.message);
                elements.statusMessage.textContent = 'Transcription cancelled.';
                resetUI();
            } 
            // Handle unexpected messages
            else {
                console.error('Unexpected message received:', data);
            }
        };
    
        socket.onclose = function() {
            console.log('WebSocket connection closed. Reconnecting...');
            setTimeout(connectWebSocket, 1000); // Reconnect after 1 seconds
        };
    
        socket.onerror = function(error) {
            console.error('WebSocket error:', error);
        };
    }
    
    function updateProgress(taskId, progress) {
        elements.progressBar.style.width = `${progress}%`;
        console.log(`Progress for task ${taskId}: ${progress}%`); // Optional: for debugging
    }
    
    // Initialize WebSocket connection
    connectWebSocket();  


    elements.cancelButton.addEventListener('click', function() {
        console.log(`Attempting to cancel task ID: ${taskId}`);
        if (taskId) {
            elements.progressBar.style.width = '0%';
            elements.loadingAnimation.style.display = 'none';
            elements.statusMessage.textContent = 'Cancelling transcription...';
            elements.cancelButton.style.display = 'none';

            // Send cancellation request via WebSocket
            if (socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ cancelTask: true, taskId: taskId }));
            } else {
                console.error('WebSocket is not open. Cannot send cancellation request.');
                elements.statusMessage.textContent = 'Unable to cancel transcription.';
            }
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
            updateProgress(100);
            elements.loadingAnimation.style.display = 'none';
            elements.statusMessage.textContent = 'Transcription complete. You can review and download your file.';
            elements.transcriptionTextArea.value = data.transcription;
            elements.transcriptionResultContainer.style.display = 'block';
            downloadUrl = data.downloadUrl;
            elements.downloadButton.style.display = 'block';
            elements.cancelButton.style.display = 'none';
            elements.repeatButton.style.display = 'block';
        })
        .catch(error => {
            elements.loadingAnimation.style.display = 'none';
            console.error('Error:', error);
            elements.statusMessage.textContent = `An error occurred: ${error.message}`;
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
