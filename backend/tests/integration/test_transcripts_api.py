"""FR-3 Dashboard CRUD over HTTP: every operation has a test (PRD §10)."""

from uuid import uuid4

import pytest

API = "/api/v1/transcripts"
PROBLEM = "application/problem+json"


def create(client, text="aaj ki meeting\nbudget discuss karenge", title=None, **headers):
    body = {"text": text} | ({"title": title} if title else {})
    r = client.post(API, json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r


# --- Create ---------------------------------------------------------------------------------------


def test_create_manual_note(client):
    r = create(client, title="Standup")
    t = r.json()
    assert r.headers["location"] == f"{API}/{t['id']}"
    assert r.headers["etag"] == f'"{t["version"]}"'
    assert (t["title"], t["engine"], t["status"], t["segment_count"]) == ("Standup", "manual", "completed", 2)
    assert t["segments"][0]["words"][:2] == [{"w": "aaj", "lang": "hi"}, {"w": "ki", "lang": "hi"}]
    assert t["hindi_ratio"] == 0.5
    # appears in History immediately
    assert client.get(API).json()["items"][0]["id"] == t["id"]


def test_create_validation_errors_are_problem_details(client):
    r = client.post(API, json={"text": ""})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith(PROBLEM)
    body = r.json()
    assert (body["code"], body["errors"][0]["field"]) == ("VALIDATION_ERROR", "text")

    r = client.post(API, json={"text": "  \n  "})
    assert (r.status_code, r.json()["code"]) == (422, "INVALID_VALUE")


def test_idempotency_key_replays_first_response(client):
    first = create(client, text="once", **{"Idempotency-Key": "k-1"})
    again = client.post(API, json={"text": "once"}, headers={"Idempotency-Key": "k-1"})
    assert (again.status_code, again.headers["idempotent-replayed"]) == (201, "true")
    assert again.json()["id"] == first.json()["id"]
    assert len(client.get(API).json()["items"]) == 1

    clash = client.post(API, json={"text": "different"}, headers={"Idempotency-Key": "k-1"})
    assert (clash.status_code, clash.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")


# --- Read -----------------------------------------------------------------------------------------


def test_list_is_newest_first_with_cursor_paging(client):
    ids = [create(client, text=f"note {i}").json()["id"] for i in range(5)]
    p1 = client.get(API, params={"limit": 2}).json()
    p2 = client.get(API, params={"limit": 2, "cursor": p1["next_cursor"]}).json()
    p3 = client.get(API, params={"limit": 2, "cursor": p2["next_cursor"]}).json()
    seen = [i["id"] for i in p1["items"] + p2["items"] + p3["items"]]
    assert seen == list(reversed(ids))
    assert p3["next_cursor"] is None


def test_default_page_size_is_20(client):
    for i in range(21):
        create(client, text=f"n{i}")
    page = client.get(API).json()
    assert len(page["items"]) == 20 and page["next_cursor"]


def test_search_and_filters(client):
    create(client, text="quarterly budget review")
    create(client, text="आज की meeting में budget")
    create(client, text="unrelated", title="Budget title only")
    create(client, text="nothing here")
    titles = {i["preview"] for i in client.get(API, params={"q": "budget"}).json()["items"]}
    assert titles == {"quarterly budget review", "आज की meeting में budget", "unrelated"}
    assert len(client.get(API, params={"q": "मीटिंग"}).json()["items"]) == 0
    assert len(client.get(API, params={"q": "आज"}).json()["items"]) == 1
    assert client.get(API, params={"engine": "sarvam"}).json()["items"] == []
    assert len(client.get(API, params={"engine": "manual"}).json()["items"]) == 4
    future = "2999-01-01T00:00:00Z"
    assert client.get(API, params={"from": future}).json()["items"] == []
    assert len(client.get(API, params={"to": future}).json()["items"]) == 4


def test_bad_query_params(client):
    assert client.get(API, params={"limit": 0}).status_code == 422
    assert client.get(API, params={"engine": "whisper"}).status_code == 422
    r = client.get(API, params={"cursor": "garbage"})
    assert (r.status_code, r.json()["code"]) == (422, "INVALID_VALUE")


def test_get_detail_and_404(client):
    t = create(client).json()
    r = client.get(f"{API}/{t['id']}")
    assert r.status_code == 200 and r.headers["etag"] == f'"{t["version"]}"'
    assert [s["seq"] for s in r.json()["segments"]] == [1, 2]
    missing = client.get(f"{API}/{uuid4()}")
    assert (missing.status_code, missing.json()["code"]) == (404, "TRANSCRIPT_NOT_FOUND")
    assert client.get(f"{API}/not-a-uuid").status_code == 422


def test_export_txt(client):
    t = create(client, title="Team Sync").json()
    r = client.get(f"{API}/{t['id']}/export")
    assert r.status_code == 200
    assert 'filename="team-sync.txt"' in r.headers["content-disposition"]
    assert r.text.startswith("Team Sync\n") and r.text.endswith("aaj ki meeting\nbudget discuss karenge\n")


def test_export_devanagari_title_uses_utf8_filename(client):
    t = create(client, title="आज की बैठक").json()
    cd = client.get(f"{API}/{t['id']}/export").headers["content-disposition"]
    assert 'filename="transcript.txt"' in cd and "filename*=UTF-8''" in cd


# --- Update ---------------------------------------------------------------------------------------


def test_rename_with_if_match(client):
    t = create(client).json()
    r = client.patch(f"{API}/{t['id']}", json={"title": "Renamed"}, headers={"If-Match": f'"{t["version"]}"'})
    assert r.status_code == 200
    assert (r.json()["title"], r.headers["etag"]) == ("Renamed", f'"{t["version"] + 1}"')


def test_patch_requires_if_match_and_rejects_stale(client):
    t = create(client).json()
    url = f"{API}/{t['id']}"
    missing = client.patch(url, json={"title": "x"})
    assert (missing.status_code, missing.json()["code"]) == (428, "PRECONDITION_REQUIRED")
    client.patch(url, json={"title": "first"}, headers={"If-Match": f'"{t["version"]}"'})
    stale = client.patch(url, json={"title": "second"}, headers={"If-Match": f'"{t["version"]}"'})
    assert (stale.status_code, stale.json()["code"]) == (412, "VERSION_CONFLICT")
    assert client.get(url).json()["title"] == "first"


def test_rename_validation(client):
    t = create(client).json()
    r = client.patch(f"{API}/{t['id']}", json={"title": "   "}, headers={"If-Match": f'"{t["version"]}"'})
    assert (r.status_code, r.json()["errors"][0]["field"]) == (422, "title")


def test_edit_segment_sets_edited_and_recomputes(client):
    t = create(client, text="meeting budget").json()
    assert t["hindi_ratio"] == 0.0
    r = client.patch(
        f"{API}/{t['id']}/segments/1",
        json={"text": "aaj ki meeting"},
        headers={"If-Match": f'"{t["version"]}"'},
    )
    body = r.json()
    assert r.status_code == 200
    assert (body["edited"], body["hindi_ratio"], body["segments"][0]["text"]) == (
        True,
        0.667,
        "aaj ki meeting",
    )
    assert client.get(API, params={"q": "aaj"}).json()["items"][0]["id"] == t["id"]  # full_text recomputed


def test_edit_unknown_segment(client):
    t = create(client).json()
    r = client.patch(
        f"{API}/{t['id']}/segments/99", json={"text": "x"}, headers={"If-Match": f'"{t["version"]}"'}
    )
    assert (r.status_code, r.json()["code"]) == (404, "SEGMENT_NOT_FOUND")


# --- Delete ---------------------------------------------------------------------------------------


def test_soft_delete_then_undo(client):
    t = create(client).json()
    assert client.delete(f"{API}/{t['id']}").status_code == 204
    assert client.get(f"{API}/{t['id']}").status_code == 404
    assert client.get(API).json()["items"] == []
    r = client.post(f"{API}/{t['id']}:restore")
    assert r.status_code == 200 and r.json()["id"] == t["id"]
    assert len(client.get(API).json()["items"]) == 1


def test_hard_delete_is_permanent(client):
    t = create(client).json()
    assert client.delete(f"{API}/{t['id']}", params={"hard": "true"}).status_code == 204
    r = client.post(f"{API}/{t['id']}:restore")
    assert (r.status_code, r.json()["code"]) == (404, "TRANSCRIPT_NOT_FOUND")


def test_delete_with_stale_if_match(client):
    t = create(client).json()
    r = client.delete(f"{API}/{t['id']}", headers={"If-Match": f'"{t["version"] + 5}"'})
    assert r.status_code == 412
    assert client.get(f"{API}/{t['id']}").status_code == 200


@pytest.mark.parametrize("method", ["get", "delete"])
def test_unknown_id_is_404(client, method):
    assert getattr(client, method)(f"{API}/{uuid4()}").status_code == 404
