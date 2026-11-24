import pytest
from starlette.websockets import WebSocketDisconnect

from hinglish.transcription.domain.session_policy import SessionPolicy

URL = "/ws/v1/transcribe"
FRAME = b"\x00" * 3200
START = {"v": 1, "type": "start", "engine": "fake", "script": "mixed"}
STOP = {"v": 1, "type": "stop"}
PING = {"v": 1, "type": "ping"}


def until(ws, type_: str) -> list[dict]:
    msgs = []
    while True:
        msg = ws.receive_json()
        msgs.append(msg)
        if msg["type"] == type_:
            return msgs


def types(msgs: list[dict]) -> list[str]:
    return [m["type"] for m in msgs]


def test_full_session_streams_partials_and_finals(client):
    with client.websocket_connect(URL) as ws:
        ws.send_json(START)
        ready = ws.receive_json()
        assert (ready["type"], ready["engine"], ready["v"]) == ("ready", "fake", 1)
        for _ in range(15):
            ws.send_bytes(FRAME)
        msgs = until(ws, "final")
        assert types(msgs) == ["latency", "partial", "partial", "final"]
        assert msgs[-1]["seq"] == 1
        assert msgs[-1]["text"] == "aaj ki meeting mein hum budget discuss karenge"
        ws.send_json(STOP)
        done = until(ws, "done")[-1]
        assert (done["reason"], done["segments"]) == ("stopped", 1)


def test_stop_finalizes_pending_speech(client):
    with client.websocket_connect(URL) as ws:
        ws.send_json(START)
        ws.receive_json()
        for _ in range(5):
            ws.send_bytes(FRAME)
        until(ws, "partial")
        ws.send_json(STOP)
        msgs = until(ws, "done")
        assert types(msgs) == ["final", "done"]
        assert msgs[0]["text"] == "aaj ki meeting"


def test_ping_pong(client):
    with client.websocket_connect(URL) as ws:
        ws.send_json(START)
        ws.receive_json()
        ws.send_json(PING)
        assert ws.receive_json()["type"] == "pong"


def test_invalid_frame_is_reported_once_and_session_continues(client):
    with client.websocket_connect(URL) as ws:
        ws.send_json(START)
        ws.receive_json()
        ws.send_bytes(b"\x00")
        ws.send_bytes(b"\x00")
        err = ws.receive_json()
        assert (err["type"], err["code"], err["fatal"]) == ("error", "FRAME_INVALID", False)
        ws.send_json(PING)
        assert ws.receive_json()["type"] == "pong"


def test_unavailable_engine_is_rejected(client):
    with client.websocket_connect(URL) as ws:
        ws.send_json({**START, "engine": "sarvam"})  # no key configured in tests
        assert ws.receive_json()["code"] == "ENGINE_NOT_AVAILABLE"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


@pytest.mark.parametrize(
    ("first", "code"),
    [(STOP, "START_REQUIRED"), ({"v": 2, "type": "start"}, "BAD_MESSAGE")],
)
def test_first_message_must_be_v1_start(client, first, code):
    with client.websocket_connect(URL) as ws:
        ws.send_json(first)
        assert ws.receive_json()["code"] == code


def test_max_duration_sends_limit_then_done(client):
    client.app.state.session_policy = SessionPolicy(max_duration_s=0.3)
    with client.websocket_connect(URL) as ws:
        ws.send_json(START)
        ws.receive_json()
        msgs = until(ws, "done")
        assert types(msgs) == ["limit", "done"]
        assert msgs[-1]["reason"] == "limit"


def test_disallowed_origin_is_refused(client):
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect(URL, headers={"origin": "http://evil.example"}),
    ):
        pass
    assert exc.value.code == 1008


def test_idle_timeout_ends_session(client):
    client.app.state.session_policy = SessionPolicy(max_duration_s=60, idle_timeout_s=0.2)
    with client.websocket_connect(URL) as ws:
        ws.send_json(START)
        ws.receive_json()
        msgs = until(ws, "done")
        assert types(msgs) == ["error", "done"]
        assert (msgs[0]["code"], msgs[-1]["reason"]) == ("IDLE_TIMEOUT", "idle")


# --- persistence (FR-2) and resume (FR-1.6) -------------------------------------------------------


def record(client, frames: int, start: dict | None = None) -> tuple[dict, list[dict]]:
    with client.websocket_connect(URL) as ws:
        ws.send_json(start or START)
        ready = ws.receive_json()
        for _ in range(frames):
            ws.send_bytes(FRAME)
        seen = until(ws, "final") if frames >= 15 else []
        ws.send_json(STOP)
        return ready, seen + until(ws, "done")


def test_finals_are_saved_before_they_are_shown(client):
    ready, msgs = record(client, 20)  # one full utterance + one pending, finalized by stop
    finals = [m for m in msgs if m["type"] == "final"]
    done = msgs[-1]
    assert ready["transcript_id"] == done["transcript_id"] and ready["resumed"] is False
    assert all(f["saved"] for f in finals)

    t = client.get(f"/api/v1/transcripts/{ready['transcript_id']}").json()
    assert [s["seq"] for s in t["segments"]] == [1, 2]
    assert [s["text"] for s in t["segments"]] == [
        "aaj ki meeting mein hum budget discuss karenge",
        "aaj ki meeting",
    ]
    assert (t["status"], t["engine"], t["title"]) == (
        "completed",
        "fake",
        "aaj ki meeting mein hum budget discuss karenge",
    )
    assert t["duration_ms"] is not None and t["hindi_ratio"] is not None


def test_resume_continues_numbering_in_the_same_transcript(client):
    first, _ = record(client, 15)
    resumed, msgs = record(client, 15, {**START, "resume_transcript_id": first["transcript_id"]})
    assert (resumed["transcript_id"], resumed["resumed"], resumed["last_seq"]) == (
        first["transcript_id"],
        True,
        1,
    )
    assert [m["seq"] for m in msgs if m["type"] == "final"] == [2]
    t = client.get(f"/api/v1/transcripts/{first['transcript_id']}").json()
    assert [s["seq"] for s in t["segments"]] == [1, 2] and t["status"] == "completed"


def test_resume_of_unknown_transcript_starts_a_new_one(client):
    ready, _ = record(client, 0, {**START, "resume_transcript_id": "6f1f0d55-34bb-4c8e-9b65-9d0f3c0f2a11"})
    assert ready["resumed"] is False
    assert client.get(f"/api/v1/transcripts/{ready['transcript_id']}").status_code == 200


def test_empty_recording_is_still_listed_as_completed(client):
    ready, msgs = record(client, 0)
    assert msgs[-1]["segments"] == 0
    item = client.get("/api/v1/transcripts").json()["items"][0]
    assert (item["id"], item["status"], item["title"]) == (ready["transcript_id"], "completed", "Untitled")
