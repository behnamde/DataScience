document.addEventListener("DOMContentLoaded", function() {
    const form = document.querySelector('#upload-form');
    const progressBarContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const statusMessage = document.getElementById('status-message');
    const transcriptionTextArea = document.getElementById('transcription-text');
    const transcriptionResultContainer = document.getElementById('transcription-result');
    const downloadBtn = document.getElementById('download-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    const repeatBtn = document.getElementById('repeat-btn');
    let downloadBlobUrl = null;

    cancelBtn.addEventListener('click', function() {
        // TODO: Implement cancellation logic with the backend
        progressBarContainer.style.display = 'none';
        statusMessage.textContent = 'Upload canceled.';
        downloadBtn.style.display = 'none';
        cancelBtn.style.display = 'none';
        repeatBtn.style.display = 'block';
        form.reset();
    });

    repeatBtn.addEventListener('click', function() {
        progressBarContainer.style.display = 'none';
        statusMessage.textContent = '';
        downloadBtn.style.display = 'none';
        cancelBtn.style.display = 'none';
        repeatBtn.style.display = 'none';
        transcriptionResultContainer.style.display = 'none';
        form.reset();
    });

    form.addEventListener('submit', function(event) {
        event.preventDefault();
        progressBarContainer.style.display = 'block';
        progressBar.style.width = '0%';
        statusMessage.textContent = 'Uploading...';
        downloadBtn.style.display = 'none';
        cancelBtn.style.display = 'block';
        repeatBtn.style.display = 'none';
        transcriptionResultContainer.style.display = 'none';

        const formData = new FormData(form);
        fetch('/transcribe/', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok.');
            return response.text();
        })
        .then(text => {
            progressBar.style.width = '100%';
            statusMessage.textContent = 'Transcription complete. You can download or review your file.';
            transcriptionTextArea.value = text;
            transcriptionResultContainer.style.display = 'block';
            downloadBlobUrl = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
            downloadBtn.style.display = 'block';
            cancelBtn.style.display = 'none';
            repeatBtn.style.display = 'block';
        })
        .catch(error => {
            console.error('Error:', error);
            progressBarContainer.style.display = 'none';
            statusMessage.textContent = 'An error occurred.';
            downloadBtn.style.display = 'none';
            cancelBtn.style.display = 'none';
            repeatBtn.style.display = 'block';
        });
    });

    downloadBtn.addEventListener('click', function() {
        if (downloadBlobUrl) {
            const link = document.createElement('a');
            link.href = downloadBlobUrl;
            link.download = "transcription.txt";
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(downloadBlobUrl);
            downloadBlobUrl = null;
            downloadBtn.style.display = 'none';
            statusMessage.textContent = 'Your file has been downloaded.';
            progressBarContainer.style.display = 'none';
            repeatBtn.style.display = 'block';
        }
    });
});
