"""Tests for the MemPalace client."""
from unittest.mock import MagicMock, patch

from ops_agent.mempalace import MemPalaceClient


def _client(response_text: str = "") -> MemPalaceClient:
    return MemPalaceClient("http://localhost:8766/mcp", wing="ops_central")


def _mock_post(text: str):
    """Return a mock httpx.post that yields text content."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": text}]},
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_search_returns_text():
    client = _client()
    with patch("httpx.post", return_value=_mock_post("result text")) as mock:
        result = client.search("proxmox nodes")
    assert result == "result text"
    call_json = mock.call_args.kwargs["json"]
    assert call_json["params"]["name"] == "mempalace_search"
    assert call_json["params"]["arguments"]["query"] == "proxmox nodes"


def test_search_returns_none_on_error():
    client = _client()
    with patch("httpx.post", side_effect=Exception("connection refused")):
        result = client.search("test")
    assert result is None


def test_add_drawer_sends_correct_payload():
    client = _client()
    with patch("httpx.post", return_value=_mock_post("stored")) as mock:
        result = client.add_drawer("proxmox", "cluster-nodes", "5 nodes in cluster")
    assert result == "stored"
    args = mock.call_args.kwargs["json"]["params"]["arguments"]
    assert args["wing"] == "ops_central"
    assert args["room"] == "proxmox"
    assert args["key"] == "cluster-nodes"
    assert args["body"] == "5 nodes in cluster"


def test_get_drawer():
    client = _client()
    with patch("httpx.post", return_value=_mock_post("drawer content")) as mock:
        result = client.get_drawer("proxmox", "cluster-nodes")
    assert result == "drawer content"
    args = mock.call_args.kwargs["json"]["params"]["arguments"]
    assert args["room"] == "proxmox"
    assert args["key"] == "cluster-nodes"


def test_query_kg():
    client = _client()
    with patch("httpx.post", return_value=_mock_post("entity facts")) as mock:
        result = client.query_kg("prox1")
    assert result == "entity facts"
    args = mock.call_args.kwargs["json"]["params"]["arguments"]
    assert args["entity"] == "prox1"


def test_context_for_task_returns_formatted_string():
    client = _client()
    with patch("httpx.post", return_value=_mock_post('{"results": [{"text": "fact"}]}')):
        ctx = client.context_for_task("list proxmox nodes")
    assert "Prior context from MemPalace" in ctx
    assert "fact" in ctx


def test_context_for_task_returns_empty_on_no_results():
    client = _client()
    with patch("httpx.post", return_value=_mock_post("")):
        ctx = client.context_for_task("something")
    assert ctx == ""


def test_context_for_task_returns_empty_on_error():
    client = _client()
    with patch("httpx.post", side_effect=Exception("down")):
        ctx = client.context_for_task("something")
    assert ctx == ""


def test_save_run_facts_slugifies_task():
    client = _client()
    with patch("httpx.post", return_value=_mock_post("ok")) as mock:
        client.save_run_facts("List all VMs in cluster", "Found 37 VMs")
    args = mock.call_args.kwargs["json"]["params"]["arguments"]
    assert args["room"] == "run-history"
    assert args["key"] == "list-all-vms-in-cluster"
    assert "List all VMs" in args["body"]
    assert "Found 37 VMs" in args["body"]


def test_save_run_facts_truncates_long_key():
    client = _client()
    long_task = "a " * 40  # very long task string
    with patch("httpx.post", return_value=_mock_post("ok")) as mock:
        client.save_run_facts(long_task, "done")
    key = mock.call_args.kwargs["json"]["params"]["arguments"]["key"]
    assert len(key) <= 60


def test_no_mempalace_url_returns_none_client():
    """When mempalace_url is empty, context_for_task should return empty string."""
    client = MemPalaceClient("", wing="ops_central")
    with patch("httpx.post") as mock:
        ctx = client.context_for_task("test")
    # With empty URL, httpx.post will raise; result is empty
    assert ctx == ""
    # But we shouldn't have made any calls
    mock.assert_not_called()
