/* 播放页：播放/暂停先用 C01 成片验证，接 show.json 后再按书取片。 */

const FILM = document.getElementById("film");
const PLAY = document.getElementById("play");

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

PLAY.addEventListener("click", toggle);
FILM.addEventListener("click", toggle);
FILM.addEventListener("play", sync);
FILM.addEventListener("pause", sync);
FILM.addEventListener("ended", sync);
