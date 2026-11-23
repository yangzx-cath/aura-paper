import json

from aura_paper.cache import Cache
from aura_paper.output import write_json
from aura_paper.schema.job import BookJobs
from aura_paper.stages.render import render
from aura_paper.video_types import VideoTask

CLIP = b"\x00\x00\x00\x18ftypmp42"


# Answer like the video service does, with a tiny stand-in for the clip.
class FakeVideo:
    model = "fake-video"

    def __init__(self, failing=()):
        self.requests = []
        self.failing = set(failing)

    def generate(self, request, path):
        self.requests.append(request)
        if request.prompt in self.failing:
            return VideoTask(task_id="t0", status="failed", error="boom")
        with open(path, "wb") as target:
            target.write(CLIP)
        return VideoTask(
            task_id=f"t{len(self.requests)}",
            status="succeeded",
            video_url="http://example/v.mp4",
            duration=request.duration,
            resolution=request.resolution or "",
        )


# Write the jobs artifact the stage reads, plus the image it names.
def make_jobs(root, names):
    book = root / "demo"
    panels = book / "panels"
    panels.mkdir(parents=True, exist_ok=True)
    (panels / "p000_0.jpg").write_bytes(b"jpg")
    shots = [
        {
            "shot": name,
            "prompt": f"prompt {name}",
            "images": [{"file": "panels/p000_0.jpg", "note": "第 1 格分镜"}],
            "duration": 5,
            "ratio": "4:3",
            "resolution": "480p",
            "audio": False,
        }
        for name in names
    ]
    book_jobs = BookJobs.from_dict(
        {
            "id": "demo",
            "ratio": "4:3",
            "resolution": "480p",
            "shots": shots,
        }
    )
    write_json("demo", "jobs", book_jobs.to_dict(), root)


def test_generates_every_shot_and_writes_the_record(tmp_path):
    make_jobs(tmp_path, ["j1", "j2"])
    client = FakeVideo()

    result = render("demo", client=client, root=tmp_path)

    assert [shot.shot for shot in result.shots] == ["j1", "j2"]
    assert [shot.task_id for shot in result.shots] == ["t1", "t2"]
    assert (tmp_path / "demo" / "clips" / "j2.mp4").read_bytes() == CLIP
    assert result.error == ""
    # The prompt, the length and the frame reach the service unchanged.
    assert client.requests[0].duration == 5
    assert client.requests[0].ratio == "4:3"
    assert client.requests[0].generate_audio is False

    saved = json.loads((tmp_path / "demo" / "render.json").read_text())
    assert saved["shots"][0]["file"] == "clips/j1.mp4"
    assert saved["shots"][0]["resolution"] == "480p"


def test_reuses_a_cached_clip(tmp_path):
    make_jobs(tmp_path, ["j1"])
    client = FakeVideo()
    cache = Cache(tmp_path / "cache")

    first = render("demo", client=client, root=tmp_path, cache=cache)
    second = render(
        "demo", client=client, root=tmp_path, cache=Cache(tmp_path / "cache")
    )

    assert len(client.requests) == 1
    assert first.shots[0].cached is False
    assert second.shots[0].cached is True
    assert (tmp_path / "demo" / "clips" / "j1.mp4").read_bytes() == CLIP


def test_records_a_failed_clip_and_keeps_going(tmp_path):
    make_jobs(tmp_path, ["j1", "j2"])
    client = FakeVideo(failing={"prompt j1"})

    result = render("demo", client=client, root=tmp_path)

    assert "j1" in result.error
    assert [shot.shot for shot in result.shots] == ["j1", "j2"]
    assert result.shots[1].task_id == "t2"
    assert (tmp_path / "demo" / "clips" / "j2.mp4").is_file()


def test_renders_one_shot_only(tmp_path):
    make_jobs(tmp_path, ["j1", "j2"])
    client = FakeVideo()

    result = render("demo", client=client, only="j2", root=tmp_path)

    assert [shot.shot for shot in result.shots] == ["j2"]
    assert len(client.requests) == 1


def test_skips_a_job_that_already_failed(tmp_path):
    make_jobs(tmp_path, ["j1"])
    jobs = json.loads((tmp_path / "demo" / "jobs.json").read_text())
    jobs["shots"][0]["error"] = "音轨太长"
    (tmp_path / "demo" / "jobs.json").write_text(json.dumps(jobs))
    client = FakeVideo()

    result = render("demo", client=client, root=tmp_path)

    assert client.requests == []
    assert result.shots[0].error == "音轨太长"
