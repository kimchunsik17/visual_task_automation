from flow_validation import issue_from_message, issue_signature, validation_issues


def test_validation_message_gets_stable_code_and_node_id():
    issue = issue_from_message(
        "n9(mergeNode)는 시작 노드가 아닌데 들어오는 엣지가 없다 — 고아 노드라 절대 실행되지 않는다."
    )

    assert issue.code == "UNREACHABLE_NODE"
    assert issue.node_id == "n9"
    assert issue.repairable is True


def test_edge_issue_extracts_edge_id():
    issue = issue_from_message("엣지 e3가 존재하지 않는 노드를 가리킨다: n99")

    assert issue.code == "DANGLING_EDGE"
    assert issue.edge_id == "e3"


def test_issue_signature_ignores_human_message_wording():
    first = validation_issues(["n1(promptNode)에 userPrompt가 없다"])
    second = validation_issues(["n1(promptNode)에 userPrompt가 비어 있다"])

    assert issue_signature(first) == issue_signature(second)
