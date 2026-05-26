from venture_metrics_agent.reasoning.router import route_message


def test_greeting_does_not_allow_tools() -> None:
    route = route_message("hi")

    assert route.intent == "casual_chat"
    assert route.needs_research is False
    assert route.allow_internal_search is False
    assert route.allow_web_search is False


def test_current_question_allows_controlled_web() -> None:
    route = route_message("What are the latest Hong Kong startup grants?")

    assert route.intent == "current_research"
    assert route.needs_research is True
    assert route.allow_internal_search is True
    assert route.allow_web_search is True


def test_help_question_does_not_allow_tools() -> None:
    route = route_message("What can you do?")

    assert route.intent == "system_help"
    assert route.needs_research is False
    assert route.allow_internal_search is False
    assert route.allow_web_search is False


def test_social_question_does_not_allow_tools() -> None:
    route = route_message("how are you?")

    assert route.intent == "casual_chat"
    assert route.needs_research is False
    assert route.allow_internal_search is False
    assert route.allow_web_search is False
