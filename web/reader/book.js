/* 播放页：播放控制与语音指令，成片先用 C01 验证。 */

const FILM = document.getElementById("film");
const PLAY = document.getElementById("play");
const MIC = document.getElementById("mic");
const TRACK = document.getElementById("track");
const FILL = document.getElementById("fill");
const TOAST = document.getElementById("toast");

// 书号来自书库的链接，录音按书存放。
const BOOK = new URLSearchParams(location.search).get("id") || "";

// 音频统一按 ASR 要的 16k 处理，浏览器开不到这个率就重采样。
const RATE = 16000;

// 一句话的判定：能量高过门限开始收，静音够久收尾。
const LEVEL = 0.015;
const QUIET_MS = 600;
const SHORTEST_MS = 300;
const LONGEST_MS = 8000;

let stream = null;
let context = null;
let source = null;
let processor = null;
let starting = false;
let listening = false;

let voiced = false;
let parts = [];
let quiet = 0;
let spoken = 0;
let timer = 0;

async function start() {
  if (starting || listening) {
    return;
  }
  if (!navigator.mediaDevices) {
    toast("语音需要 HTTPS 访问");
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
        sampleRate: RATE,
      },
    });
  } catch (error) {
    toast("没有拿到麦克风权限");
    return;
  } finally {
    starting = false;
  }

  const Voice = window.AudioContext || window.webkitAudioContext;
  context = new Voice({ sampleRate: RATE });
  source = context.createMediaStreamSource(stream);
  processor = context.createScriptProcessor(1024, 1, 1);
  processor.addEventListener("audioprocess", hear);
  source.connect(processor);

  // 处理器要接到输出才会跑，用零增益节点把声音闷掉。
  const mute = context.createGain();
  mute.gain.value = 0;
  processor.connect(mute);
  mute.connect(context.destination);

  reset();
  listening = true;
  mark(true);
  toast("语音已打开，说“暂停”或“播放”");
}

function stop() {
  listening = false;
  mark(false);
  processor.disconnect();
  source.disconnect();
  context.close();
  for (const track of stream.getTracks()) {
    track.stop();
  }
  processor = null;
  source = null;
  context = null;
  stream = null;
  reset();
}

// 每块音频先进句缓冲，静音够久就把这句送去识别。
function hear(event) {
  const block = event.inputBuffer.getChannelData(0);
  const pcm = resample(block, context.sampleRate);
  const level = rms(pcm);
  const ms = (pcm.length / RATE) * 1000;

  if (!voiced) {
    if (level < LEVEL) {
      return;
    }
    voiced = true;
    parts = [pcm];
    quiet = 0;
    spoken = ms;
    return;
  }

  parts.push(pcm);
  spoken += ms;
  quiet = level < LEVEL ? quiet + ms : 0;
  if (quiet >= QUIET_MS || spoken >= LONGEST_MS) {
    finish();
  }
}

// 一句话说完就上送，太短的当噪声丢掉。
function finish() {
  const speech = spoken - quiet;
  voiced = false;
  if (speech < SHORTEST_MS) {
    reset();
    return;
  }
  const pcm = toPcm16(parts);
  reset();
  send(pcm);
}

// 服务端只回文本，指令在这里匹配。
async function send(pcm) {
  const url = `/api/qa/audio?book=${encodeURIComponent(BOOK)}`;
  toast("正在识别…");
  const reply = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "audio/pcm" },
    body: pcm,
  });
  if (!reply.ok) {
    toast("语音识别失败");
    return;
  }
  const data = await reply.json();
  obey(data.text);
}

// 取整句里的关键词，宁可不动也不误判。
function obey(text) {
  const said = String(text || "").replace(/[\s，。！？、,.!?]/g, "");
  if (!said) {
    toast("没听清，再说一次");
    return;
  }
  toast(`听到：${said}`);
  if (said.includes("暂停") || said.includes("停")) {
    FILM.pause();
    return;
  }
  const play = ["播放", "继续", "开始"].some((word) => said.includes(word));
  if (play) {
    FILM.play();
  }
}

function reset() {
  voiced = false;
  parts = [];
  quiet = 0;
  spoken = 0;
}

// 音频上下文不一定能开到 16k，按比例线性插值。
function resample(input, from) {
  if (from === RATE) {
    // 处理器的输入缓冲会被下一块覆盖，必须自己留一份。
    return input.slice();
  }
  const length = Math.round((input.length * RATE) / from);
  const out = new Float32Array(length);
  for (let i = 0; i < length; i += 1) {
    const pos = (i * from) / RATE;
    const at = Math.floor(pos);
    const next = Math.min(at + 1, input.length - 1);
    const frac = pos - at;
    out[i] = input[at] * (1 - frac) + input[next] * frac;
  }
  return out;
}

// 一句话是否有人声，看这一块的均方根。
function rms(samples) {
  let sum = 0;
  for (const value of samples) {
    sum += value * value;
  }
  return Math.sqrt(sum / Math.max(1, samples.length));
}

// 浮点样本折成服务端要的 16 位小端 PCM。
function toPcm16(parts) {
  let total = 0;
  for (const part of parts) {
    total += part.length;
  }
  const samples = new Int16Array(total);
  let at = 0;
  for (const part of parts) {
    for (const value of part) {
      const clamped = Math.max(-1, Math.min(1, value));
      samples[at] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      at += 1;
    }
  }
  return samples;
}

// 收听状态只改按钮外观与读屏文案。
function mark(live) {
  MIC.classList.toggle("is-live", live);
  MIC.setAttribute("aria-pressed", String(live));
  MIC.setAttribute("aria-label", live ? "关闭语音" : "语音助手");
}

// 识别结果用浮框提示，2.6 秒后自己收起。
function toast(text) {
  TOAST.textContent = text;
  TOAST.classList.add("is-shown");
  clearTimeout(timer);
  timer = setTimeout(() => {
    TOAST.classList.remove("is-shown");
  }, 2600);
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
  if (listening) {
    stop();
    return;
  }
  start();
});
