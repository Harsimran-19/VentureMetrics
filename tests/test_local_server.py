from venture_metrics_agent.ui.local_server import _clean_history


def test_clean_history_filters_invalid_items() -> None:
    assert _clean_history([{"role": "user", "content": "hi"}, {"role": "system", "content": "x"}, "bad"]) == [
        {"role": "user", "content": "hi"}
    ]
