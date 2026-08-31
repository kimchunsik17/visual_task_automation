# -*- coding: utf-8 -*-
"""새 템플릿을 짧게 쓰기 위한 헬퍼. 노드/엣지 조립과 검증만 한다."""
import sys
sys.path.insert(0, "/home/ubuntu/app/backend")

_seq = {"n": 0}


def N(t, **data):
    _seq["n"] += 1
    return {"id": f"n{_seq['n']}", "type": t, "data": data, "position": None}


def chain(*nodes):
    """일자로 잇는다. 대부분의 템플릿이 이 모양이다."""
    edges = []
    for a, b in zip(nodes, nodes[1:]):
        edges.append({"id": f"e-{a['id']}-{b['id']}", "source": a["id"], "target": b["id"],
                      "sourceHandle": None, "targetHandle": None})
    return list(nodes), edges


def link(a, b, source_handle=None, target_handle=None):
    return {"id": f"e-{a['id']}-{b['id']}-{source_handle or ''}", "source": a["id"],
            "target": b["id"], "sourceHandle": source_handle, "targetHandle": target_handle}


def G(title, description, nodes, edges):
    return {"title": title, "description": description, "nodes": nodes, "edges": edges}


# 자주 쓰는 조각들
def llm(system, model="gpt-4o-mini"):
    return N("llmNode", model=model, systemPrompt=system)


def out():
    return N("outputNode")


def start():
    return N("startNode")


def ask(label, test):
    return N("dynamicInputNode", inputLabel=label, testValue=test)


def sched(cron="0 9 * * *"):
    return N("scheduleNode", cronExpression=cron)
