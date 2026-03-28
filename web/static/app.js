const video = document.getElementById('webcam');
const canvas = document.getElementById('capture-canvas');
const ctx = canvas.getContext('2d');
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const statusText = document.getElementById('status-text');
const statusOverlay = document.getElementById('status-overlay');
const currentGuessText = document.getElementById('current-guess-text');
const matchIndicator = document.getElementById('match-indicator');
const reasoningEl = document.getElementById('reasoning');
const confidenceBadge = document.getElementById('confidence-badge');
const frameCountEl = document.getElementById('frame-count');
const guessCountEl = document.getElementById('guess-count');
const guessLimitEl = document.getElementById('guess-limit');
const guessList = document.getElementById('guess-list');
const fpsSlider = document.getElementById('fps-slider');
const fpsValue = document.getElementById('fps-value');
const targetWordInput = document.getElementById('target-word');
const totalTokensEl = document.getElementById('total-tokens');
const inputTokensEl = document.getElementById('input-tokens');
const outputTokensEl = document.getElementById('output-tokens');
const sentFramePreview = document.getElementById('sent-frame-preview');
const sentFrameCtx = sentFramePreview.getContext('2d');

const MAX_GUESSES = 10;

let intervalId = null;
let stream = null;
let frameCount = 0;
let guessCount = 0;
let totalTokens = 0;
let inputTokens = 0;
let outputTokens = 0;
let isProcessing = false;
let solved = false;
let wrongGuesses = [];

fpsSlider.addEventListener('input', () => {
    fpsValue.textContent = fpsSlider.value;
    if (intervalId) {
        clearInterval(intervalId);
        intervalId = setInterval(captureAndAnalyze, 1000 / parseFloat(fpsSlider.value));
    }
});

btnStart.addEventListener('click', startAnalyzing);
btnStop.addEventListener('click', stopAnalyzing);

// Open camera immediately on page load
startCamera();

document.getElementById('btn-next-word').addEventListener('click', () => {
    solved = false;
    wrongGuesses = [];
    guessCount = 0;
    frameCount = 0;
    guessCountEl.textContent = '0';
    guessLimitEl.textContent = MAX_GUESSES;
    frameCountEl.textContent = '0';
    targetWordInput.value = '';
    currentGuessText.textContent = '-';
    currentGuessText.className = 'guess-display';
    matchIndicator.textContent = '';
    matchIndicator.className = 'match-indicator hidden';
    reasoningEl.style.display = 'none';
    confidenceBadge.textContent = '';
    document.querySelector('.current-guess').classList.remove('solved');
    document.getElementById('btn-next-word').style.display = 'none';
    // Clear guess history
    guessList.innerHTML = '<p class="empty-state">No guesses yet. Start the camera!</p>';
    // Reset agent's internal wrong-guess tracking
    fetch('/api/reset', { method: 'POST' });
    targetWordInput.focus();
});

async function startCamera() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: 'user' }
        });
        video.srcObject = stream;
        await video.play();

        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
    } catch (err) {
        statusText.textContent = 'Camera access denied';
        console.error('Camera error:', err);
    }
}

function startAnalyzing() {
    if (intervalId) return;
    btnStart.disabled = true;
    btnStop.disabled = false;
    statusOverlay.classList.add('active');
    statusText.textContent = 'Get ready... (2s warmup)';

    // 2-second warmup before first frame
    setTimeout(() => {
        statusText.textContent = 'Analyzing...';
        const fps = parseFloat(fpsSlider.value);
        intervalId = setInterval(captureAndAnalyze, 1000 / fps);
    }, 2000);
}

function stopAnalyzing() {
    if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
    }
    btnStart.disabled = false;
    btnStop.disabled = true;
    statusOverlay.classList.remove('active');
    statusText.textContent = 'Stopped';
}

async function captureAndAnalyze() {
    if (isProcessing || solved || guessCount >= MAX_GUESSES) {
        if (guessCount >= MAX_GUESSES && !solved) {
            statusText.textContent = `Out of guesses (${MAX_GUESSES}/${MAX_GUESSES})`;
            stopAnalyzing();
        }
        return;
    }
    isProcessing = true;

    ctx.drawImage(video, 0, 0);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.4);

    // Show captured frame in preview
    sentFramePreview.width = canvas.width;
    sentFramePreview.height = canvas.height;
    sentFrameCtx.drawImage(canvas, 0, 0);

    frameCount++;
    frameCountEl.textContent = frameCount;
    statusText.textContent = `Analyzing frame #${frameCount}... (${guessCount}/${MAX_GUESSES} guesses)`;

    try {
        const resp = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: dataUrl, wrong_guesses: wrongGuesses }),
        });

        const data = await resp.json();

        if (data.error) {
            addGuessToLog('Error: ' + data.error, 'error', null);
        } else if (data.guess) {
            // Check if this is a duplicate of a wrong guess (model ignored instruction)
            const guessLower = data.guess.toLowerCase();
            const isDuplicate = wrongGuesses.some(w => w.toLowerCase() === guessLower);

            if (!isDuplicate) {
                guessCount++;
                guessCountEl.textContent = guessCount;
                guessLimitEl.textContent = MAX_GUESSES - guessCount;
            }

            currentGuessText.textContent = data.guess;
            currentGuessText.classList.add('pulse');
            setTimeout(() => currentGuessText.classList.remove('pulse'), 600);

            const isMatch = checkMatch(data.guess);

            if (isDuplicate) {
                addGuessToLog(data.guess + ' (duplicate, not counted)', 'error', data.confidence);
            } else {
                addGuessToLog(data.guess, isMatch ? 'match' : 'guess', data.confidence);
            }

            if (isMatch) {
                solved = true;
                matchIndicator.textContent = 'CORRECT!';
                matchIndicator.className = 'match-indicator correct';
                currentGuessText.className = 'guess-display correct-guess';
                statusText.textContent = `Correct in ${guessCount} guess${guessCount > 1 ? 'es' : ''}!`;
                document.querySelector('.current-guess').classList.add('solved');
                document.getElementById('btn-next-word').style.display = 'inline-block';
                stopAnalyzing();
            } else {
                matchIndicator.textContent = 'NOT QUITE...';
                matchIndicator.className = 'match-indicator wrong';
                // Track this as a wrong guess (avoid duplicates in the list)
                if (!isDuplicate) {
                    wrongGuesses.push(data.guess);
                }
            }

            // Show reasoning and confidence
            if (data.reasoning) {
                reasoningEl.textContent = data.reasoning;
                reasoningEl.style.display = 'block';
            }
            if (data.confidence) {
                confidenceBadge.textContent = data.confidence.toUpperCase();
                confidenceBadge.className = 'confidence-badge conf-' + data.confidence.toLowerCase();
            }

            // Check if out of guesses
            if (guessCount >= MAX_GUESSES && !solved) {
                statusText.textContent = `Out of guesses! (${MAX_GUESSES}/${MAX_GUESSES})`;
                document.getElementById('btn-next-word').style.display = 'inline-block';
                stopAnalyzing();
            }
        }

        // Update token counts
        if (data.usage) {
            inputTokens += data.usage.request_tokens || 0;
            outputTokens += data.usage.response_tokens || 0;
            totalTokens += data.usage.total_tokens || 0;
            totalTokensEl.textContent = totalTokens.toLocaleString();
            inputTokensEl.textContent = inputTokens.toLocaleString();
            outputTokensEl.textContent = outputTokens.toLocaleString();
        }
    } catch (err) {
        addGuessToLog('Network error: ' + err.message, 'error');
    }

    isProcessing = false;
}

function addGuessToLog(text, type, confidence) {
    const emptyState = guessList.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    const entry = document.createElement('div');
    entry.className = `guess-entry ${type}`;

    const time = new Date().toLocaleTimeString();
    const confBadge = confidence ? `<span class="log-conf conf-${confidence.toLowerCase()}">${confidence}</span>` : '';
    entry.innerHTML = `<span class="guess-time">${time}</span>${confBadge}<span class="guess-text">${escapeHtml(text)}</span>`;

    guessList.insertBefore(entry, guessList.firstChild);

    // Keep max 50 entries
    while (guessList.children.length > 50) {
        guessList.removeChild(guessList.lastChild);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function checkMatch(guess) {
    const target = targetWordInput.value.trim().toLowerCase();
    if (!target) return false;
    const g = guess.toLowerCase();
    return g.includes(target) || target.includes(g);
}
