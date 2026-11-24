/* 播放页：播放控制与录音上传，成片先用 C01 验证。 */

const FILM = document.getElementById("film");
const PLAY = document.getElementById("play");
const MIC = document.getElementById("mic");
const TRACK = document.getElementById("track");
const FILL = document.getElementById("fill");
const SUBTITLE = document.getElementById("subtitle");

// 书号来自书库的链接，录音按书存放。
const BOOK = new URLSearchParams(location.search).get("id") || "";

// 容器按浏览器支持顺序探测：Chrome 给 webm，Safari 给 mp4。
const TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];

let stream = null;
let recorder = null;
let chunks = [];
let starting = false;

async function start() {
  if (starting) {
    return;
  }
  if (!navigator.mediaDevices) {
    say("语音需要 HTTPS 访问");
    return;
  }
  starting = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
        sampleRate: 16000,
      },
    });
  } catch (error) {
    say("没有拿到麦克风权限");
    return;
  } finally {
    starting = false;
  }

  FILM.pause();
  chunks = [];
  const type = pickType();
  const options = type ? { mimeType: type } : {};
  recorder = new MediaRecorder(stream, options);
  recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size) {
      chunks.push(event.data);
    }
  });
  recorder.addEventListener("stop", save);
  recorder.start();
  mark(true);
}

function stop() {
  if (!recorder || recorder.state !== "recording") {
    return;
  }
  recorder.stop();
  mark(false);
  for (const track of stream.getTracks()) {
    track.stop();
  }
  stream = null;
}

// 录音停下后整段上传，服务端只负责按书落盘。
async function save() {
  const blob = new Blob(chunks, { type: recorder.mimeType });
  chunks = [];
  const url = `/api/qa/audio?book=${encodeURIComponent(BOOK)}`;
  const reply = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": blob.type },
    body: blob,
  });
  if (!reply.ok) {
    say("录音上传失败");
    return;
  }
  say("录音已保存");
}

// 空字符串表示交给浏览器自己挑容器。
function pickType() {
  for (const type of TYPES) {
    if (MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return "";
}

// 录音状态只改按钮外观与读屏文案。
function mark(live) {
  MIC.classList.toggle("is-live", live);
  MIC.setAttribute("aria-pressed", String(live));
  MIC.setAttribute("aria-label", live ? "停止录音" : "麦克风");
}

// 提示先借字幕行显示，接上问答后改到对话抽屉。
function say(text) {
  SUBTITLE.textContent = text;
}

function toggle() {
  if (FILM.paused) {
    FILM.play();
    return;
  }
  FILM.pause();
}

// 播完或中途暂停时按钮要跟着视频状态走。
function sync() {
  const playing = !FILM.paused;
  PLAY.classList.toggle("is-playing", playing);
  PLAY.setAttribute("aria-label", playing ? "暂停" : "播放");
}

// 进度按视频自己的总时长折算，一条成片不需要额外提供时长。
function draw() {
  const total = FILM.duration;
  const ratio = total ? FILM.currentTime / total : 0;
  FILL.style.width = `${ratio * 100}%`;
}

// 指针位置换算成时间，按到哪就跳到哪。
function seek(event) {
  const total = FILM.duration;
  if (!total) {
    return;
  }
  const box = TRACK.getBoundingClientRect();
  const offset = (event.clientX - box.left) / box.width;
  const ratio = Math.min(1, Math.max(0, offset));
  FILM.currentTime = ratio * total;
  draw();
}

let dragging = false;

TRACK.addEventListener("pointerdown", (event) => {
  dragging = true;
  TRACK.setPointerCapture(event.pointerId);
  seek(event);
});

TRACK.addEventListener("pointermove", (event) => {
  if (dragging) {
    seek(event);
  }
});

TRACK.addEventListener("pointerup", (event) => {
  dragging = false;
  TRACK.releasePointerCapture(event.pointerId);
});

TRACK.addEventListener("pointercancel", () => {
  dragging = false;
});

PLAY.addEventListener("click", toggle);
FILM.addEventListener("click", toggle);
FILM.addEventListener("play", sync);
FILM.addEventListener("pause", sync);
FILM.addEventListener("ended", sync);
FILM.addEventListener("timeupdate", draw);
FILM.addEventListener("loadedmetadata", draw);

// 录音中亮起按钮，再按一次关掉；真正的采集后面接。
MIC.addEventListener("click", () => {
  if (recorder && recorder.state === "recording") {
    stop();
    return;
  }
  start();
});
