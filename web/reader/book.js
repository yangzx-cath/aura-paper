/* 播放页：播放控制与语音指令，成片先用 C01 验证。 */

const FILM = document.getElementById("film");
const PLAY = document.getElementById("play");
const MIC = document.getElementById("mic");
const TRACK = document.getElementById("track");
const FILL = document.getElementById("fill");
const SUBTITLE = document.getElementById("subtitle");
const META = document.getElementById("meta");
const STAGE = document.getElementById("stage");
const SPOT_BOX = document.getElementById("spot-box");
const SPOT_PIN = document.getElementById("spot-pin");
const SPOT_CARD = document.getElementById("spot-card");
const SPOT_NAME = document.getElementById("spot-name");
const SPOT_INTRO = document.getElementById("spot-intro");

// 年龄分级按书的语言给，书名以外的信息都写在这一行里。
const AGES = { zh: "4–8 岁", en: "6–10 岁" };
const LANGUAGES = { zh: "中文", en: "英文" };

// 预先生成的固定话术，放在 resources/voice 下。
const CLIPS = {
  found: "/static/voice/found.wav",
  unknown: "/static/voice/unknown.wav",
  unheard: "/static/voice/unheard.wav",
  think: "/static/voice/think.wav",
};

// 书号来自书库的链接，录音按书存放。
const BOOK = new URLSearchParams(location.search).get("id") || "";

// 音频统一按 ASR 要的 16k 处理，浏览器开不到这个率就重采样。
const RATE = 16000;

// 一句话的判定：能量高过门限开始收，静音够久收尾。
const LEVEL = 0.015;
const QUIET_MS = 350;
// 完整的单字（“停”）约 400 ms，短于 250 ms 的声响多是碰撞。
const SHORTEST_MS = 250;
const LONGEST_MS = 8000;

// 起说前多带几块，第一个字才不会被削掉。
const PRE_ROLL = 8;

// 句尾补一段静音，ASR 对孤立的短词才容易切出来。
const PAD_MS = 200;

// 一整句里最响的一块低于这个值，就当噪声，不上传也不计费。
const PEAK_MIN = 0.04;

// 一句结束后先静一静，避免余音连着再触发。
const COOLDOWN_MS = 800;

// 音频按 100 ms 一片送给端点，太碎的帧它不接受。
const SLICE = 1600;

// 点一下和拖动分开：位移小于 10px、时长小于 400ms 才算点。
const TAP_MOVE = 10;
const TAP_MS = 400;

// 说明卡停多久自动收起。
const SPOT_MS = 9000;

// 识别最多等这么久，超时就当没认出来，免得一次卡住后面都点不动。
// 视觉模型的慢速调用可以到十秒以上，留足余量。
const SPOT_WAIT = 15000;

// 送去识别的帧宽度：原片 1280 宽，缩到 896 后体积减半，模型看细节仍够。
const FRAME_WIDTH = 896;

let stream = null;
let context = null;
let source = null;
let processor = null;
let starting = false;
let listening = false;

let voiced = false;
let quiet = 0;
let spoken = 0;
let loudest = 0;
let holdUntil = 0;
let socket = null;
let busy = false;
let queued = [];
let slice = [];
let sliceLen = 0;
let recent = [];
let pages = [];
let answering = null;

// 发布清单里的字幕，和现在已经显示的那一条。
let cues = [];
let shown = -1;
let marked = null;

// 触控：按下时的位置，和已经打开的那张卡。
let tapStart = null;
let spotBusy = false;
let spotPlaying = false;
let spotPoint = null;
let spotBox = [];
let spotTimer = 0;

async function start() {
  if (starting || listening) {
    return;
  }
  if (!navigator.mediaDevices) {
    console.warn("语音需要 HTTPS 访问");
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
    console.warn("没有拿到麦克风权限");
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
}

function stop() {
  listening = false;
  mark(false);
  closeStream();
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

// 每块音频在起说时开流，之后边收边送。
function hear(event) {
  const block = event.inputBuffer.getChannelData(0);
  const pcm = resample(block, context.sampleRate);
  const level = rms(pcm);
  const ms = (pcm.length / RATE) * 1000;

  // 自己正在说话时清空预录，免得把话术尾巴当成开场白。
  if (!voiced) {
    if (busy || answering || performance.now() < holdUntil) {
      recent = [];
      return;
    }
    keep(pcm);
    if (level < LEVEL) {
      return;
    }
    voiced = true;
    loudest = level;
    openStream();
    for (const earlier of recent) {
      feed(earlier);
    }
    recent = [];
    quiet = 0;
    spoken = ms;
    return;
  }

  feed(pcm);
  spoken += ms;
  loudest = Math.max(loudest, level);
  quiet = level < LEVEL ? quiet + ms : 0;
  if (quiet >= QUIET_MS || spoken >= LONGEST_MS) {
    finish();
  }
}

// 起说前留几块，触发时一起送。
function keep(pcm) {
  recent.push(pcm);
  if (recent.length > PRE_ROLL) {
    recent.shift();
  }
}

// 攒够一片再发，剩下的那半片收尾时补上。
function feed(pcm) {
  slice.push(pcm);
  sliceLen += pcm.length;
  if (sliceLen < SLICE) {
    return;
  }
  const bytes = toPcm16(slice);
  slice = [];
  sliceLen = 0;
  write(bytes);
}

// 流还没通时先攒着，连上后一起补齐。
function write(bytes) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(bytes);
    return;
  }
  queued.push(bytes);
}

// 说完就通知端点收尾，太短的当噪声直接丢掉。
function finish() {
  const speech = spoken - quiet;
  voiced = false;
  if (sliceLen > 0) {
    write(toPcm16(slice));
  }
  slice = [];
  sliceLen = 0;
  recent = [];
  quiet = 0;
  spoken = 0;
  holdUntil = performance.now() + COOLDOWN_MS;
  if (speech < SHORTEST_MS || loudest < PEAK_MIN || !socket) {
    closeStream();
    loudest = 0;
    return;
  }
  write(new Int16Array((RATE * PAD_MS) / 1000));
  if (socket.readyState !== WebSocket.OPEN) {
    closeStream();
    return;
  }
  socket.send(JSON.stringify({ type: "end" }));
}

// 起说就建流，服务端从第一个字节就开始识别。
function openStream() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const query = encodeURIComponent(BOOK);
  const ws = new WebSocket(`${scheme}://${location.host}/ws/qa?book=${query}`);
  socket = ws;
  busy = true;
  ws.addEventListener("open", () => {
    for (const bytes of queued) {
      ws.send(bytes);
    }
    queued = [];
  });
  ws.addEventListener("message", (event) => {
    // 上一句的回包晚到时，别拿它去触发下一句的指令。
    if (socket === ws) {
      receive(event);
    }
  });
  ws.addEventListener("close", () => {
    if (socket === ws) {
      socket = null;
      busy = false;
    }
  });
}

function closeStream() {
  if (socket) {
    socket.close();
    socket = null;
  }
  busy = false;
  queued = [];
}

// 中间结果先交给指令匹配，最终文本再走一遍完整流程。
function receive(event) {
  const data = JSON.parse(event.data);
  if (data.type === "text") {
    command(clean(data.text));
    return;
  }
  if (data.type === "done") {
    busy = false;
    obey(data.text);
    return;
  }
  busy = false;
}

// 最终文本先试命令，再试本地检索，最后交给模型。
async function obey(text) {
  const said = clean(text);
  if (!said) {
    playClip("unheard");
    return;
  }
  const heard = tidy(text);
  if (command(said)) {
    return;
  }
  if (find(said)) {
    return;
  }
  await ask(heard);
}

// 中间结果和最终文本都走这里，宁可不动也不误判。
function command(said) {
  const text = said.toLowerCase();
  const pause = ["暂停", "停", "pause", "stop"];
  if (pause.some((word) => text.includes(word))) {
    dismissSpot();
    FILM.pause();
    return true;
  }
  const play = ["播放", "继续", "开始", "play", "resume", "continue"];
  if (play.some((word) => text.includes(word))) {
    dismissSpot();
    FILM.play();
    return true;
  }
  return false;
}

// 比对用：去掉空格和标点，中文和英文命令落到同一种写法。
function clean(text) {
  return String(text || "").replace(/[\s，。！？、,.!?]/g, "");
}

// 展示和提问用：只收掉多余空白，英文单词之间的空格要留着。
function tidy(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

// 找画面或台词：先看问的是哪一种，命中就跳过去。
function find(said) {
  const at = said.search(/找到|查找|搜索|高亮|帮我找|找找/);
  if (at < 0) {
    return false;
  }
  const head = said.slice(at);
  const slot = trimSlot(head.replace(/^(找到|查找|搜索|帮我找|找找|高亮)/, ""));
  if (!slot) {
    playClip("unheard");
    return true;
  }
  const lineFirst = /高亮|查找|搜索|这句/.test(said);
  const line = bestLine(slot);
  const page = best(slot);
  if (lineFirst && line) {
    showLine(line, slot);
    return true;
  }
  if (page) {
    showPage(page);
    return true;
  }
  if (line) {
    showLine(line, slot);
    return true;
  }
  return false;
}

// 本地定不了的，把整本书的页面表交给模型去选或回答。
async function ask(text) {
  const reply = await post(text);
  if (!reply || reply.kind === "none") {
    playClip("unknown");
    return;
  }
  dismissSpot();
  const page = pageOf(reply.page);
  if (page) {
    FILM.pause();
    FILM.currentTime = page.start;
    marked = null;
    draw();
  }
  if (reply.kind === "answer") {
    playAnswer(reply.audio);
    return;
  }
  if (!page) {
    playClip("unknown");
    return;
  }
  playClip("found");
}

// 问一次服务端，网络或接口出错都当作没找到。
async function post(text) {
  try {
    const reply = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        book: BOOK,
        query: text,
        page: currentPage(),
      }),
    });
    if (!reply.ok) {
      return null;
    }
    return await reply.json();
  } catch (error) {
    return null;
  }
}

function pageOf(number) {
  return pages.find((row) => row.page === number) || null;
}

// 回答或固定话术都用同一个播放器，播的时候把视频音量压低。
function playAudio(url) {
  if (!url) {
    return;
  }
  if (answering) {
    answering.pause();
  }
  const clip = new Audio(url);
  answering = clip;
  FILM.volume = 0.2;
  clip.addEventListener("ended", () => endVoice(clip));
  clip.addEventListener("error", () => endVoice(clip));
  clip.play().catch(() => endVoice(clip));
}

// 模型给的答案带 base64 音频，单独包一层。
function playAnswer(encoded) {
  if (encoded) {
    playAudio(`data:audio/wav;base64,${encoded}`);
  }
}

// 固定话术：找到一段，答不上来另一段。
function playClip(kind) {
  playAudio(CLIPS[kind]);
}

function endVoice(clip) {
  if (answering !== clip) {
    return;
  }
  FILM.volume = 1;
  answering = null;
  holdUntil = performance.now() + COOLDOWN_MS;
}

// 台词短，命中比例够高才算找到。
function bestLine(slot) {
  const pairs = [...bigrams(slot)];
  const needed = pairs.length === 1
    ? 1
    : Math.max(2, Math.ceil(pairs.length * 0.5));
  let top = null;
  let topScore = 0;
  for (const cue of cues) {
    const hay = normalize(cue.text);
    let hit = 0;
    for (const pair of pairs) {
      if (hay.includes(pair)) {
        hit += 1;
      }
    }
    if (hit >= needed && hit > topScore) {
      topScore = hit;
      top = cue;
    }
  }
  return top;
}

// 跳到那一句，并把命中的片段标出来。
function showLine(line, slot) {
  dismissSpot();
  FILM.pause();
  FILM.currentTime = line.start;
  draw();
  const index = cues.indexOf(line);
  const spot = locate(line.text, slot);
  marked = spot ? { index, from: spot.from, to: spot.to } : null;
  shown = -1;
  speak();
  playClip("found");
}

// 在原文里找到要标的位置，标点不参与比对。
function locate(text, slot) {
  let flat = "";
  const map = [];
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (MARKS.includes(ch)) {
      continue;
    }
    flat += ch;
    map.push(i);
  }
  const at = flat.indexOf(slot);
  if (at < 0) {
    return null;
  }
  return { from: map[at], to: map[at + slot.length - 1] + 1 };
}

function showPage(page) {
  dismissSpot();
  FILM.pause();
  FILM.currentTime = page.start;
  marked = null;
  draw();
  playClip("found");
}

// 把“...的画面”“...的那一页”这类尾巴去掉，只留要找的东西。
function trimSlot(text) {
  const flat = normalize(text);
  return flat.replace(/(的那一页|的画面|那一页|这幅画|画面|一页|的图)$/g, "");
}

// 二元组打分：命中要多，稀有的词组权重高，常见的词权重低。
function best(slot) {
  const pairs = [...bigrams(slot)];
  const hays = pages.map((page) => haystack(page));
  const now = currentPage();
  // 短语越短越容易撞上常见词，要求命中的比例也越高。
  const needed = pairs.length === 1
    ? 1
    : Math.max(2, Math.ceil(pairs.length * 0.5));
  let top = null;
  let topScore = 0;
  for (let index = 0; index < pages.length; index += 1) {
    const hay = hays[index];
    let hit = 0;
    let score = 0;
    for (const pair of pairs) {
      if (!hay.includes(pair)) {
        continue;
      }
      hit += 1;
      const seen = hays.filter((row) => row.includes(pair)).length;
      score += 1 / seen;
    }
    if (hit < needed) {
      continue;
    }
    // 故事往后走，当前页之后的优先级高一点。
    if (pages[index].page >= now) {
      score += 0.05;
    }
    if (score > topScore) {
      topScore = score;
      top = pages[index];
    }
  }
  return top;
}

// 一页的可检索文本：台词、画面描述和角色名。
function haystack(page) {
  const names = (page.cast || []).join("");
  return normalize(`${page.text}${page.desc}${names}`);
}

// 当前播到第几页，用作检索的起点。
function currentPage() {
  let page = 0;
  for (const item of pages) {
    if (item.start <= FILM.currentTime + 0.01) {
      page = item.page;
    }
  }
  return page;
}

function bigrams(text) {
  const set = new Set();
  if (text.length < 2) {
    set.add(text);
    return set;
  }
  for (let i = 0; i + 2 <= text.length; i += 1) {
    set.add(text.slice(i, i + 2));
  }
  return set;
}

// 个位数字，两位数的拼法见 number()。
const DIGITS = {
  零: 0, 一: 1, 二: 2, 两: 2, 三: 3, 四: 4,
  五: 5, 六: 6, 七: 7, 八: 8, 九: 9,
};

// 检索时去掉的字符：空白、标点和引号。
const MARKS = " \t\n\r，。！？、,.!?：“”\"'…—";

// 检索用的统一写法：去标点空白，中文数字换成阿拉伯数字。
function normalize(text) {
  const flat = flatten(text).toLowerCase();
  return flat.replace(
    /[零一二两三四五六七八九十]+(?=[块个只张页])/g,
    (run) => String(number(run))
  );
}

// 去掉标点与空白，保留字序。
function flatten(text) {
  let out = "";
  for (const ch of String(text || "")) {
    if (!MARKS.includes(ch)) {
      out += ch;
    }
  }
  return out;
}

// 一到九十九的中文数字，超出范围的当作没写。
function number(run) {
  if (run === "十") {
    return 10;
  }
  const at = run.indexOf("十");
  if (at < 0) {
    return DIGITS[run[0]] ?? 0;
  }
  const tens = at === 0 ? 1 : DIGITS[run[at - 1]] ?? 0;
  const ones = at === run.length - 1 ? 0 : DIGITS[run[at + 1]] ?? 0;
  return tens * 10 + ones;
}

function reset() {
  voiced = false;
  quiet = 0;
  spoken = 0;
  loudest = 0;
  slice = [];
  sliceLen = 0;
  recent = [];
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

// 书名、视频和字幕都从发布清单里读，路径由书 id 拼出来。
async function load() {
  if (!BOOK) {
    SUBTITLE.textContent = "从书库选一本书";
    return;
  }
  try {
    const url = `/api/books/${encodeURIComponent(BOOK)}/publish`;
    const reply = await fetch(url);
    if (!reply.ok) {
      SUBTITLE.textContent = "这本书还没有发布";
      return;
    }
    const show = await reply.json();
    if (!show.film) {
      SUBTITLE.textContent = "发布清单里没有视频";
      return;
    }
    if (show.title) {
      document.title = show.title;
    }
    FILM.src = pub(show.film);
    if (show.cover) {
      FILM.poster = pub(show.cover);
    }
    pages = show.pages || [];
    cues = await subtitles(pub(show.vtt || "subtitles.vtt"));
    shown = -1;
    label(show);
  } catch (error) {
    SUBTITLE.textContent = "读不到这本书";
  }
}

// 顶部那一行：4–8 岁 · 2:20 · 中文，缺哪个就少写哪个。
function label(show) {
  const language = String(show.language || "").trim();
  const pieces = [];
  if (AGES[language]) {
    pieces.push(AGES[language]);
  }
  if (show.seconds) {
    pieces.push(clock(show.seconds));
  }
  if (LANGUAGES[language]) {
    pieces.push(LANGUAGES[language]);
  }
  if (!pieces.length) {
    return;
  }
  META.textContent = pieces.join(" · ");
  META.hidden = false;
}

// 秒换成 m:ss。
function clock(seconds) {
  const total = Math.round(Number(seconds) || 0);
  const rest = String(total % 60).padStart(2, "0");
  return `${Math.floor(total / 60)}:${rest}`;
}

// 发布目录里的一个文件。
function pub(name) {
  return `/api/books/${encodeURIComponent(BOOK)}/pub/${name}`;
}

// 读出字幕文件；读不到就当这本书没有字幕。
async function subtitles(url) {
  try {
    const reply = await fetch(url);
    if (!reply.ok) {
      return [];
    }
    return parseVtt(await reply.text());
  } catch (error) {
    return [];
  }
}

// WebVTT 拆成按时间排好的一条条，说话人从 voice span 里取。
function parseVtt(text) {
  const lines = String(text).replace(/\r/g, "").split("\n");
  const list = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = /^(\S+)\s+-->\s+(\S+)/.exec(lines[index]);
    if (!match) {
      continue;
    }
    const body = [];
    index += 1;
    while (index < lines.length && lines[index].trim() !== "") {
      body.push(lines[index]);
      index += 1;
    }
    const said = voice(body.join(" "));
    list.push({
      start: seconds(match[1]),
      end: seconds(match[2]),
      who: said.who,
      text: said.text,
    });
  }
  return list;
}

// <v 旁白>这一句</v> 拆成说话人和正文，没有标记就整句都算正文。
function voice(line) {
  const match = /^<v\s+([^>]*)>([\s\S]*)<\/v>$/.exec(line.trim());
  if (!match) {
    return { who: "", text: plain(line) };
  }
  return { who: match[1].trim(), text: plain(match[2]) };
}

// 00:01:02.345 换成秒，顺手把转义过的符号改回来。
function seconds(stamp) {
  const parts = String(stamp).split(":");
  const last = Number(parts.pop() || 0);
  const minutes = Number(parts.pop() || 0);
  const hours = Number(parts.pop() || 0);
  return hours * 3600 + minutes * 60 + last;
}

// 一行里的换行折成空格，空格不留在标点前面。
function plain(text) {
  return String(text)
    .replace(/\s*\n\s*/g, " ")
    .replace(/([a-z)"'’])([.?!])([A-Z])/g, "$1$2 $3")
    .replace(/ ([.,!?;:…，。、；：！？])/g, "$1")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .trim();
}

// 只在这一条换了的时候写字幕，否则每次 timeupdate 都要重排。
function speak() {
  const index = cueAt(FILM.currentTime);
  if (index === shown) {
    return;
  }
  shown = index;
  if (index < 0) {
    SUBTITLE.textContent = "";
    SUBTITLE.className = "subtitle";
    marked = null;
    return;
  }
  paint(cues[index], index);
}

// 命中片段单独包一层 mark，其余文字原样写入。
function paint(cue, index) {
  const kind = cue.who === "旁白" ? "narrator" : "cast";
  SUBTITLE.className = `subtitle subtitle--${kind}`;
  if (!marked || marked.index !== index) {
    marked = null;
    SUBTITLE.textContent = cue.text;
    return;
  }
  const before = cue.text.slice(0, marked.from);
  const hit = cue.text.slice(marked.from, marked.to);
  const after = cue.text.slice(marked.to);
  const mark = document.createElement("mark");
  mark.className = "subtitle-hit";
  mark.textContent = hit;
  // 字幕行是 grid 容器，多出来的节点会各占一行，所以整句包进一个 span。
  const line = document.createElement("span");
  line.replaceChildren(before, mark, after);
  SUBTITLE.replaceChildren(line);
}

// 字幕按时间排好且不重叠，用二分找当前这条。
function cueAt(at) {
  let low = 0;
  let high = cues.length - 1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const cue = cues[middle];
    if (at < cue.start) {
      high = middle - 1;
    } else if (at >= cue.end) {
      low = middle + 1;
    } else {
      return middle;
    }
  }
  return -1;
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
FILM.addEventListener("play", sync);
FILM.addEventListener("pause", sync);
FILM.addEventListener("ended", sync);
FILM.addEventListener("timeupdate", draw);
FILM.addEventListener("loadedmetadata", draw);

// 空格切播放与暂停；焦点在按钮或链接上时交给它们自己处理。
document.addEventListener("keydown", (event) => {
  if (event.code !== "Space" || event.repeat) {
    return;
  }
  const target = event.target;
  if (target instanceof Element && target.closest("button, a")) {
    return;
  }
  event.preventDefault();
  toggle();
});

// 字幕跟着同一个时钟走，跳转后也要立刻对一次。
FILM.addEventListener("timeupdate", speak);
FILM.addEventListener("seeked", speak);
FILM.addEventListener("loadedmetadata", speak);

// 视频一真的继续播、或者位置一换，卡片就不再对应这一帧了，收起来。
FILM.addEventListener("playing", dismissSpot);
FILM.addEventListener("seeked", dismissSpot);

// 点画面就是触控：截下这一帧，标出点的位置，交给服务端认。
STAGE.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) {
    return;
  }
  tapStart = {
    x: event.clientX,
    y: event.clientY,
    at: performance.now(),
  };
});

STAGE.addEventListener("pointerup", (event) => {
  if (!tapStart) {
    return;
  }
  const moved = Math.hypot(
    event.clientX - tapStart.x,
    event.clientY - tapStart.y
  );
  const held = performance.now() - tapStart.at;
  tapStart = null;
  if (moved > TAP_MOVE || held > TAP_MS) {
    return;
  }
  tap(event);
});

async function tap(event) {
  // 卡片开着时，再点一下先收起来，不急着认新的东西。
  if (!SPOT_CARD.hidden) {
    closeSpot();
    return;
  }
  if (spotBusy || !FILM.videoWidth) {
    return;
  }
  const point = framePoint(event);
  if (!point) {
    return;
  }

  spotBusy = true;
  spotPlaying = !FILM.paused;
  FILM.pause();
  const at = FILM.currentTime;
  const image = frameImage(point);
  // 认的过程只出声，不占画面；结果回来再弹卡片。
  awaitSpot(point);
  playClip("think");

  try {
    const gate = new AbortController();
    const timer = setTimeout(() => gate.abort(), SPOT_WAIT);
    const reply = await fetch("/api/touch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: gate.signal,
      body: JSON.stringify({
        book: BOOK,
        time: at,
        x: point.x,
        y: point.y,
        image,
      }),
    });
    clearTimeout(timer);
    if (!spotPoint) {
      return;
    }
    if (!reply.ok) {
      showSpot("", "没有认出来，再点一次试试");
      return;
    }
    const found = await reply.json();
    if (!found.topic) {
      showSpot("", found.note || "这里没有特别要说的事情");
      return;
    }
    spotBox = found.box || [];
    showSpot(found.topic.name, found.topic.intro);
    paintSpot(point);
  } catch (error) {
    if (spotPoint) {
      showSpot("", "没有连上识别服务");
    }
  } finally {
    spotBusy = false;
    armSpot();
  }
}

// 屏幕坐标换成画面里的比例；落在黑边上就当没点。
function framePoint(event) {
  const box = FILM.getBoundingClientRect();
  const scale = Math.min(
    box.width / FILM.videoWidth,
    box.height / FILM.videoHeight
  );
  const width = FILM.videoWidth * scale;
  const height = FILM.videoHeight * scale;
  const left = box.left + (box.width - width) / 2;
  const top = box.top + (box.height - height) / 2;
  const x = (event.clientX - left) / width;
  const y = (event.clientY - top) / height;
  if (x < 0 || x > 1 || y < 0 || y > 1) {
    return null;
  }
  const stage = STAGE.getBoundingClientRect();
  return {
    x,
    y,
    width,
    height,
    left: left - stage.left,
    top: top - stage.top,
  };
}

// 截下当前这一帧，在点的位置画一个圆圈，让模型看见手指在哪。
function frameImage(point) {
  const scale = Math.min(1, FRAME_WIDTH / FILM.videoWidth);
  const width = Math.round(FILM.videoWidth * scale);
  const height = Math.round(FILM.videoHeight * scale);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(FILM, 0, 0, width, height);

  const cx = point.x * width;
  const cy = point.y * height;
  const ring = width * 0.022;
  const line = Math.max(3, width * 0.004);
  ctx.lineWidth = line;
  ctx.strokeStyle = "rgba(16, 22, 19, 0.55)";
  ctx.beginPath();
  ctx.arc(cx, cy, ring + line, 0, Math.PI * 2);
  ctx.stroke();
  ctx.strokeStyle = "#ffffff";
  ctx.beginPath();
  ctx.arc(cx, cy, ring, 0, Math.PI * 2);
  ctx.stroke();
  return canvas.toDataURL("image/jpeg", 0.8);
}

function awaitSpot(point) {
  spotPoint = point;
  spotBox = [];
  SPOT_BOX.hidden = true;
  SPOT_CARD.hidden = true;
  // point.left 是视频左上角，圆圈要画在点的位置。
  SPOT_PIN.style.left = `${point.left + point.x * point.width}px`;
  SPOT_PIN.style.top = `${point.top + point.y * point.height}px`;
  SPOT_PIN.hidden = false;
  armSpot();
}

// 结果回来才亮卡片，名称与介绍一起写进去再定位。
function showSpot(name, intro) {
  if (!spotPoint) {
    return;
  }
  SPOT_PIN.hidden = true;
  SPOT_CARD.hidden = false;
  SPOT_NAME.textContent = name || "";
  SPOT_NAME.hidden = !name;
  SPOT_INTRO.textContent = intro || "";
  placeSpot();
  armSpot();
}

// 卡片贴外框的右边，放不下就翻到左边；没有外框时贴点击点。
function spotAnchor() {
  if (!spotBox.length) {
    return { left: spotPoint.left, top: spotPoint.top, width: 0, height: 0 };
  }
  return {
    left: spotPoint.left + spotBox[0] * spotPoint.width,
    top: spotPoint.top + spotBox[1] * spotPoint.height,
    width: (spotBox[2] - spotBox[0]) * spotPoint.width,
    height: (spotBox[3] - spotBox[1]) * spotPoint.height,
  };
}

// 卡片先放物体右边，越界就翻到另一边。
function placeSpot() {
  const stage = STAGE.getBoundingClientRect();
  const card = SPOT_CARD.getBoundingClientRect();
  const spot = spotAnchor();
  const gap = 14;
  const margin = 12;
  let left = spot.left + spot.width + gap;
  if (left + card.width > stage.width - margin) {
    left = spot.left - card.width - gap;
  }
  let top = spot.top;
  if (top + card.height > stage.height - margin) {
    top = spot.top + spot.height - card.height;
  }
  const maxLeft = stage.width - card.width - margin;
  const maxTop = stage.height - card.height - margin;
  SPOT_CARD.style.left = `${clamp(left, margin, maxLeft)}px`;
  SPOT_CARD.style.top = `${clamp(top, margin, maxTop)}px`;
}

function clamp(value, low, high) {
  return Math.max(low, Math.min(value, Math.max(low, high)));
}

// 外框按归一化坐标画到画面上，跟着播放器的实际显示区域走。
function paintSpot(point) {
  if (!spotBox.length) {
    SPOT_BOX.hidden = true;
    return;
  }
  const left = spotBox[0] * point.width;
  const top = spotBox[1] * point.height;
  SPOT_BOX.style.left = `${point.left + left}px`;
  SPOT_BOX.style.top = `${point.top + top}px`;
  SPOT_BOX.style.width = `${(spotBox[2] - spotBox[0]) * point.width}px`;
  SPOT_BOX.style.height = `${(spotBox[3] - spotBox[1]) * point.height}px`;
  SPOT_BOX.hidden = false;
}

function closeSpot(resume = true) {
  clearTimeout(spotTimer);
  SPOT_CARD.hidden = true;
  SPOT_BOX.hidden = true;
  SPOT_PIN.hidden = true;
  spotBox = [];
  spotPoint = null;
  if (resume && spotPlaying && FILM.paused) {
    FILM.play();
  }
  spotPlaying = false;
}

function armSpot() {
  clearTimeout(spotTimer);
  spotTimer = setTimeout(closeSpot, SPOT_MS);
}

// 语音接管时收起卡片，但不顺手把视频播起来。
function dismissSpot() {
  if (spotPoint) {
    closeSpot(false);
  }
}

// 录音中亮起按钮，再按一次关掉；真正的采集后面接。
MIC.addEventListener("click", () => {
  if (listening) {
    stop();
    return;
  }
  start();
});

load();
