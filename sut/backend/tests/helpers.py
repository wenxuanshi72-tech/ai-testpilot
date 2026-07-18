from __future__ import annotations

from typing import Any, Protocol, cast


class JsonResponse(Protocol):
    def get_json(self) -> Any: ...


def response_json(response: JsonResponse) -> dict[str, Any]:
    payload = response.get_json()
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)
