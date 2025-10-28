// ----- CANVAS -----
const canvas = document.getElementById("drawingCanvas");
const ctx = canvas.getContext("2d");

// Dopasowanie rozmiaru canvas do elementu
function resizeCanvas() {
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

let drawing = false;
let color = document.getElementById("colorPicker").value;

canvas.addEventListener("mousedown", (e) => {
    drawing = true;
    ctx.beginPath();
    ctx.moveTo(e.offsetX, e.offsetY);
});
canvas.addEventListener("mousemove", (e) => {
    if (drawing) {
        ctx.lineTo(e.offsetX, e.offsetY);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();
    }
});
canvas.addEventListener("mouseup", () => {
    drawing = false;
});
canvas.addEventListener("mouseout", () => {
    drawing = false;
});

// Zmiana koloru
document.getElementById("colorPicker").addEventListener("change", (e) => {
    color = e.target.value;
});

// Wyczyść canvas
document.getElementById("clearCanvas").addEventListener("click", () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
});


// ----- CHAT -----
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatBox = document.getElementById("chatBox");

chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (message === "") return;

    // Dodaj wiadomość do czatu (lokalnie)
    const msgDiv = document.createElement("div");
    msgDiv.textContent = message;
    msgDiv.classList.add("mb-1");
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    chatInput.value = "";
});

// ----- TIMER -----
const timerEl = document.getElementById("timer");
let timeLeft = parseInt(timerEl.textContent);

function countdown() {
    if (timeLeft > 0) {
        timeLeft -= 1;
        timerEl.textContent = timeLeft;
    } else {
        clearInterval(timerInterval);
        alert("Koniec rundy!");
    }
}

const timerInterval = setInterval(countdown, 1000);
