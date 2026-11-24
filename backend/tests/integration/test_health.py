def test_live(client):
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_reports_roles_and_vendors(client):
    body = client.get("/api/v1/health/ready").json()
    assert body["roles"] == ["api", "gateway", "worker"]
    assert body["vendors"] == {"sarvam": False, "groq": False}
