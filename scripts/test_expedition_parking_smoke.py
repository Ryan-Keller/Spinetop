from __future__ import annotations

from datetime import datetime, timezone

from dashboard_api import app


def _post_json(client, path: str, payload: dict[str, object]) -> dict[str, object]:
    response = client.post(path, json=payload)
    try:
        body = response.get_json(silent=True) or {}
    except Exception:
        body = {}
    if response.status_code >= 400:
        raise RuntimeError(f"POST {path} failed with HTTP {response.status_code}: {body}")
    if not body.get("ok", False):
        raise RuntimeError(f"POST {path} returned a non-ok payload: {body}")
    return body


def main() -> int:
    app.config["TESTING"] = True
    objective = f"parking smoke {datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    with app.test_client() as client:
        created = _post_json(client, "/api/expeditions", {"objective": objective})
        mission = str(created["item"]["mission_id"])

        parked = _post_json(
            client,
            f"/api/expeditions/{mission}/parking",
            {
                "status": "parked",
                "reason": "smoke test parking",
                "resume_hint": "resume explicitly",
            },
        )
        if parked["parking_status"]["status"] != "parked":
            raise RuntimeError(f"mission did not park: {parked}")

        input_result = _post_json(
            client,
            f"/api/expeditions/{mission}/input",
            {"content": "input while parked"},
        )
        if input_result["mission"]["parking_status"]["status"] != "parked":
            raise RuntimeError(f"mission auto-resumed on input: {input_result}")

        chat_result = _post_json(
            client,
            f"/api/expeditions/{mission}/chat",
            {"content": "chat while parked", "quick_reply": "Proceed with assumptions"},
        )
        if chat_result["item"]["parking_status"]["status"] != "parked":
            raise RuntimeError(f"mission auto-resumed on chat: {chat_result}")

        resumed = _post_json(
            client,
            f"/api/expeditions/{mission}/parking",
            {"status": "active", "reason": "resume explicitly"},
        )
        if resumed["parking_status"]["status"] != "active":
            raise RuntimeError(f"mission did not resume explicitly: {resumed}")

    print("expedition parking smoke passed")
    print(f"mission_id={mission}")
    print("routes=POST /api/expeditions, /api/expeditions/<id>/input, /api/expeditions/<id>/chat, /api/expeditions/<id>/parking")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
