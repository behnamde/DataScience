document.addEventListener("DOMContentLoaded", function() {
    let socket = io();
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

    function connectSocketIO() {
        // Connect to Socket.IO server
        socket.on('connect', function() {
            console.log("Socket.IO connection established");
        });

        socket.on('progress_update', function(data) {
            let timestamp = new Date();
            console.log("Socket.IO message received:", data);
            console.log("time =", timestamp);

            if (data.taskId && data.hasOwnProperty('progress')) {
                taskId = data.taskId;
                updateProgress(taskId, data.progress);
            }
        });

        socket.on('message', function(data) {
            if (data.message && data.message.includes('Cancellation requested')) {
                resetUI();
                console.log(data.message);
                elements.statusMessage.textContent = 'Transcription cancelled.';
            }
        });

        socket.on('error', function(data) {
            console.error('Error message received:', data);
            elements.statusMessage.textContent = `Error: ${data.error}`;
        });

        socket.on('disconnect', function() {
            console.log('Socket.IO connection disconnected. Attempting to reconnect...');
            socket.connect(); // Reconnect
        });
    }
    
    function updateProgress(taskId, progress) {
        elements.progressBar.style.width = `${progress}%`;
        elements.statusMessage.textContent = `Processing Percentage: ${data.progress}%`;
        console.log(`Progress for task ${taskId}: ${progress}%`); // Optional: for debugging
    }
    
    // Initialize Socket.IO connection
    connectSocketIO();  


    // elements.cancelButton.addEventListener('click', function() {
    //     console.log(`Attempting to cancel task ID: ${taskId}`);
    //     if (taskId) {
    //         // Send cancellation request via Socket.IO
    //         if (socket.connected) {
    //             socket.emit('cancel_task', { taskId: taskId });
    //         } else {
    //             console.error('Socket.IO is not connected. Cannot send cancellation request.');
    //             elements.statusMessage.textContent = 'Unable to cancel transcription.';
    //         }
    //         resetUI();
    //         elements.statusMessage.textContent = 'Cancelling transcription...';
    //         elements.repeatButton.style.display = 'block';
    //     } else {
    //         console.error('No transcription task to cancel.');
    //         elements.statusMessage.textContent = 'No ongoing transcription task found.';
    //     }
    // });

    elements.cancelButton.addEventListener('click', function() {
        var confirmation = confirm('Are you sure you want to cancel?');
        if (confirmation) {
            // Code to handle the cancellation
            console.log(`Attempting to cancel task ID: ${taskId}`);
            if (taskId) {
            // Send cancellation request via Socket.IO
            if (socket.connected) {
                socket.emit('cancel_task', { taskId: taskId });
            } else {
                console.error('Socket.IO is not connected. Cannot send cancellation request.');
                elements.statusMessage.textContent = 'Unable to cancel transcription.';
            }
            resetUI();
            elements.statusMessage.textContent = 'Cancelling transcription...';
            elements.repeatButton.style.display = 'block';
            } else {
                console.error('No transcription task to cancel.');
                elements.statusMessage.textContent = 'No ongoing transcription task found.';
            }
        } else {
            console.log('Cancellation aborted.');
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
