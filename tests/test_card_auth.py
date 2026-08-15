import json

import httpx
import pytest

from scripts.card_auth import CardAuthClient, derive_key, machine_id, mask_card_key


def test_machine_id_is_stable():
    assert machine_id() == machine_id()
    assert len(machine_id()) >= 8


def test_derive_key_is_deterministic_and_salt_sensitive():
    key_a = derive_key("BYDSJ-ABCD-EFGH-JKLM-NPQR", machine_id(), b"salt1")
    key_b = derive_key("BYDSJ-ABCD-EFGH-JKLM-NPQR", machine_id(), b"salt1")
    key_c = derive_key("BYDSJ-ABCD-EFGH-JKLM-NPQR", machine_id(), b"salt2")
    assert key_a == key_b
    assert key_a != key_c
    assert len(key_a) == 32


def test_mask_card_key_hides_middle():
    assert (
        mask_card_key("BYDSJ-ABCD-EFGH-JKLM-NPQR")
        == "BYDSJ-XXXX-XXXX-XXXX-NPQR"
    )
    assert mask_card_key("") == ""
    assert mask_card_key("abc") == "***"


def _client_with_handler(handler):
    transport = httpx.MockTransport(handler)
    return CardAuthClient("https://example.test", http_client=httpx.Client(transport=transport))


def test_activate_success_returns_expiry():
    def handler(request):
        body = json.loads(request.content)
        assert body["key"].startswith("BYDSJ-")
        return httpx.Response(200, json={"ok": True, "bound": True, "expires_at": None})

    client = _client_with_handler(handler)
    result = client.activate("BYDSJ-ABCD-EFGH-JKLM-NPQR", machine_id())
    assert result["ok"] is True


def test_activate_bound_elsewhere_raises():
    def handler(request):
        return httpx.Response(409, json={"detail": "卡密已绑定其他机器，请联系管理员解绑"})

    client = _client_with_handler(handler)
    with pytest.raises(Exception, match="已绑定其他机器"):
        client.activate("BYDSJ-ABCD-EFGH-JKLM-NPQR", machine_id())
