/* 播放页：播放/暂停先用 C01 成片验证，接 show.json 后再按书取片。 */

const FILM = document.getElementById("film");
const PLAY = document.getElementById("play");
const TRACK = document.getElementById("track");
const FILL = document.getElementById("fill");

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
