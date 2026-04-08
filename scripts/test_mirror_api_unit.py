from __future__ import annotations

import re

import mirror_api
import save_api


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class _FakeApi:
    @staticmethod
    def _normalize_question_text(text: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split())

    @staticmethod
    def _operator_save_text(text: str) -> str | None:
        return save_api.extract_save_text(text)

    @staticmethod
    def _operator_invoke_role_text(message: str, quick_reply: str | None = None) -> str | None:
        return None

    @staticmethod
    def normalize_mission_id(mission_id: str) -> str:
        return str(mission_id or "").strip()

    @staticmethod
    def _sync_mission_storage() -> None:
        return None

    @staticmethod
    def _read_mirror_notes(mission_id: str):
        return [
            {"artifact_id": "note_002", "text": "Dinner idea: grilled chicken bowls.", "created_at": "2026-04-07T01:00:00+00:00", "artifact_kind": "operator_save"},
            {"artifact_id": "note_001", "text": "Dog sitting note: use a treat lure.", "created_at": "2026-04-07T00:30:00+00:00", "artifact_kind": "operator_save"},
        ]


def _test_plan_and_semantic_match() -> None:
    api = _FakeApi()
    recent = mirror_api.build_mirror_retrieval_plan(api, "[Concierge] show what I saved recently")
    semantic = mirror_api.concierge_mirror_retrieval_result(api, "mission_mirror_api", "what have I saved about dinner?")
    no_match = mirror_api.concierge_mirror_retrieval_result(api, "mission_mirror_api", "what have I saved about volcanoes?")

    _assert(recent == {"is_mirror_retrieval": True, "query_text": "", "mode": "recent"}, f"recent retrieval plan changed: {recent}")
    _assert(semantic is not None and semantic["matches"][0]["artifact_id"] == "note_002", f"semantic retrieval should match dinner note first: {semantic}")
    _assert(semantic is not None and semantic["query"] == "dinner", f"semantic retrieval should preserve cleaned query: {semantic}")
    _assert(no_match is not None and no_match["matches"] == [], f"no-match retrieval should stay empty: {no_match}")


def main() -> int:
    _test_plan_and_semantic_match()
    print("mirror_api_unit_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
