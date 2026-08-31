import datetime
import json as _json
import os
import uuid
from node_registry import node_registry


def _find_downstream_schema_fields(start_id, node_dict, forward_edges, max_hops=8):
    """templateAnalyzerNode 뒤에 이미 useStructuredOutput+jsonSchema(고정된 필드 이름)를
    가진 llmNode가 있으면 그 property 이름들을 반환한다.

    템플릿이 없어서 즉석 생성해야 할 때, 이 스키마를 무시하고 별도 LLM 호출로 필드 이름을
    "따로" 지어내면 두 곳이 서로 다른 이름을 짓게 되어(예: 템플릿엔 fullName, 채움 JSON엔
    name) fileModifierNode가 그 필드를 하나도 못 채우는 문제가 생긴다(실제로 겪음 — 자기소개서
    hwpx에 experience 하나만 우연히 이름이 겹쳐서 채워지고 나머지는 전부 {{key}}로 남았음).
    그래서 이미 정해진 다운스트림 스키마가 있으면 그걸 그대로 템플릿 필드 이름으로 재사용해서
    애초에 어긋날 일이 없게 한다.
    """
    visited = set()
    queue = [start_id]
    hops = 0
    while queue and hops < max_hops:
        next_queue = []
        for nid in queue:
            for target_id, _handle in forward_edges.get(nid, []):
                if target_id in visited:
                    continue
                visited.add(target_id)
                tgt = node_dict.get(target_id)
                if not tgt:
                    continue
                if tgt.get('type') == 'llmNode':
                    data = tgt.get('data', {})
                    if data.get('useStructuredOutput') and data.get('jsonSchema'):
                        try:
                            schema = _json.loads(data['jsonSchema'])
                        except Exception:
                            schema = None
                        if isinstance(schema, dict):
                            props = schema.get('properties')
                            if isinstance(props, dict) and props:
                                return list(props.keys())
                next_queue.append(target_id)
        queue = next_queue
        hops += 1
    return None

def _confine_to_uploads(path: str) -> str:
    """서식·출력 경로를 uploads/ 밑으로 가둔다.

    예전 규칙은 "uploads/ 로 시작하지 않으면 basename 을 붙인다" 였는데, 그래서
    `uploads/../../.env` 처럼 **uploads/ 로 시작하면서 밖으로 나가는** 경로는 그대로 통과했다
    (2026-08-31 보안 감사). 상위 이동이 섞여 있으면 basename 만 남긴다.
    실행 시점 방어는 graph.py 프리앰블의 `_safe_user_path` 가 한 겹 더 한다.
    """
    if not path:
        return path
    normalized = path.replace('\\', '/')
    parts = [seg for seg in normalized.split('/') if seg not in ('', '.')]
    if '..' in parts or not normalized.startswith('uploads/'):
        return 'uploads/' + os.path.basename(normalized.replace('..', '')) if os.path.basename(normalized.replace('..', '')) else 'uploads/'
    return normalized


@node_registry.register('templateAnalyzerNode')
def generate_template_analyzer_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Template Analyzer Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    template_file = node.get('data', {}).get('template_path', '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\\', '/')
    # output_file과 동일하게 uploads/ 밑으로 정규화한다 — 안 그러면 챗봇이 지어낸 "자기소개서_템플릿.hwpx"
    # 처럼 디렉터리 없는 경로가 서버 실행 위치(backend/) 바로 밑에 그대로 생겨 uploads/ 밖에 파일이
    # 흩어지는 문제가 있었다(실제로 backend/ 루트에 파일이 생기는 것을 확인함).
    template_file = _confine_to_uploads(template_file)
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    import re")
    lines.append(f"{indent}    import json")
    lines.append(f"{indent}    import os")
    lines.append(f"{indent}    template_ext = \"{template_file}\".lower()")
    lines.append(f"{indent}    extracted_keys = set()")
    lines.append(f"{indent}    full_text = ''")
    # 챗봇이 지어낸 template_path("계약서_템플릿.docx" 같은)는 실제로 업로드된 적이 없어 파일이
    # 존재하지 않는 경우가 흔하다(예: project 30에서 실제로 겪은 "No such file or directory").
    # 사용자가 직접 파일을 올릴 때까지 기다리지 않고, 파일명에서 문서 종류를 추측해 생성형 LLM으로
    # 그럴듯한 빈칸 필드 이름을 지어낸 뒤 실제 .hwpx/.docx 파일을 즉석에서 만들어 그 자리에 채운다.
    # 그러면 아래 스캔 로직이 방금 만든 진짜 파일을 그대로 읽어 {{key}} 목록을 뽑아낸다.
    downstream_fields = _find_downstream_schema_fields(node_id, node_dict, forward_edges)
    # 재생성은 **파일이 없을 때만** 한다. 예전에는 "파일은 있는데 그 안의 {{key}}가 다운스트림
    # 스키마와 절반도 안 겹치면 낡은 템플릿"으로 보고 다시 만들었는데, generate_hwpx_template 의
    # 첫 인자가 출력 경로가 아니라 **템플릿 경로 자체**라서 사용자가 올린 서식이 빈칸만 있는 새
    # 문서로 교체됐다. 되돌릴 수 없는 손실이라 그 분기를 걷어냈다 — 키가 안 맞는 것은 분석 결과로
    # 알리면 되지, 남의 파일을 지울 이유가 아니다.
    lines.append(f"{indent}    _tmpl_needs_regen_{node_id} = not os.path.exists(\"{template_file}\")")
    lines.append(f"{indent}    if _tmpl_needs_regen_{node_id} and (template_ext.endswith('.hwpx') or template_ext.endswith('.docx')):")
    if downstream_fields:
        # 뒤에 이미 필드 이름이 고정된 useStructuredOutput 스키마(llmNode)가 있으면, 별도로
        # LLM을 불러 이름을 새로 짓지 않고 그 스키마의 키를 그대로 재사용한다 — 그래야 나중에
        # fileModifierNode가 채울 JSON의 키와 방금 만든 템플릿의 {{key}}가 반드시 일치한다.
        fields_literal = _json.dumps(downstream_fields, ensure_ascii=False)
        lines.append(f"{indent}        _tmpl_fields_{node_id} = {fields_literal}")
    else:
        lines.append(f"{indent}        try:")
        lines.append(f"{indent}            _tmpl_llm_{node_id} = create_runtime_chat_model(model='gpt-4o-mini', max_retries=0)")
        lines.append(f"{indent}            _tmpl_prompt_{node_id} = \"다음 파일명으로 미루어 짐작되는 문서 종류에 맞는 서식 빈칸 필드 이름들을 만들어라: '\" + \"{template_file}\" + \"'. 영어 소문자 camelCase 키 이름으로 최대 8개, 콤마로만 구분해서 다른 설명 없이 한 줄로 출력해라. 예: candidateName,summary,motivation\"")
        lines.append(f"{indent}            _tmpl_resp_{node_id} = _tmpl_llm_{node_id}.invoke(_tmpl_prompt_{node_id})")
        lines.append(f"{indent}            _tmpl_text_{node_id} = _tmpl_resp_{node_id}.content if hasattr(_tmpl_resp_{node_id}, 'content') else str(_tmpl_resp_{node_id})")
        lines.append(f"{indent}            _tmpl_fields_{node_id} = [f.strip() for f in _tmpl_text_{node_id}.replace(chr(10), ',').split(',') if f.strip()]")
        lines.append(f"{indent}        except Exception:")
        lines.append(f"{indent}            _tmpl_fields_{node_id} = []")
        lines.append(f"{indent}        if not _tmpl_fields_{node_id}:")
        lines.append(f"{indent}            _tmpl_fields_{node_id} = ['content']")
    lines.append(f"{indent}        _tmpl_title_{node_id} = os.path.splitext(os.path.basename(\"{template_file}\"))[0].replace('_템플릿', '').replace('_template', '')")
    lines.append(f"{indent}        from template_generator import generate_hwpx_template, generate_docx_template")
    lines.append(f"{indent}        if template_ext.endswith('.hwpx'):")
    lines.append(f"{indent}            generate_hwpx_template(\"{template_file}\", _tmpl_fields_{node_id}, title=_tmpl_title_{node_id})")
    lines.append(f"{indent}        else:")
    lines.append(f"{indent}            generate_docx_template(\"{template_file}\", _tmpl_fields_{node_id}, title=_tmpl_title_{node_id})")
    # .hwp(구버전 바이너리)는 윈도우 전용 COM 자동화(pythoncom+pyhwpx)로만 다룰 수 있어 이
    # 리눅스 서버에서는 여전히 지원하지 않는다. 반면 .hwpx는 docx/pptx처럼 zip으로 묶인
    # XML(OWPML) 포맷이라 순수 파이썬(zipfile+xml.etree)만으로 읽고 쓸 수 있다 — tokenizerNode의
    # .hwpx 읽기 로직과 동일한 방식으로 텍스트를 추출해서 {{key}} 플레이스홀더를 찾는다.
    lines.append(f"{indent}    if template_ext.endswith('.hwp'):")
    lines.append(f"{indent}        raise ValueError('HWP(.hwp) 서식 파일은 현재 지원하지 않습니다. HWPX(.hwpx)나 Word(.docx) 서식을 사용해주세요.')")
    # HWPX 는 공용 엔진이 읽는다(documents/hwpx). 예전에는 여기서 `<hp:t>` 텍스트를 이어 붙인 뒤
    # 정규식으로 찾았는데, 그러면 문단·표 경계를 넘어 이어 붙여 없는 자리표시자를 만들어 냈고
    # 반대로 run 이 쪼개진 자리표시자는 텍스트 사이에 공백이 끼어 못 찾았다.
    lines.append(f"{indent}    elif template_ext.endswith('.hwpx'):")
    lines.append(f"{indent}        from documents import hwpx as _hwpx_engine")
    lines.append(f"{indent}        for _k in _hwpx_engine.template_keys(\"{template_file}\"):")
    lines.append(f"{indent}            extracted_keys.add(_k)")
    lines.append(f"{indent}    elif template_ext.endswith('.docx') or template_ext.endswith('.doc'):")
    lines.append(f"{indent}        from docx import Document as _DocxDocument")
    lines.append(f"{indent}        _docx_doc = _DocxDocument(\"{template_file}\")")
    lines.append(f"{indent}        for p in _docx_doc.paragraphs:")
    lines.append(f"{indent}            if p.text: full_text += p.text + ' '")
    lines.append(f"{indent}        for _tbl in _docx_doc.tables:")
    lines.append(f"{indent}            for _row in _tbl.rows:")
    lines.append(f"{indent}                for _cell in _row.cells:")
    lines.append(f"{indent}                    if _cell.text: full_text += _cell.text + ' '")
    lines.append(f"{indent}    elif template_ext.endswith('.xlsx') or template_ext.endswith('.xls'):")
    lines.append(f"{indent}        import openpyxl")
    lines.append(f"{indent}        wb = openpyxl.load_workbook(\"{template_file}\")")
    lines.append(f"{indent}        for sheet in wb.worksheets:")
    lines.append(f"{indent}            for row in sheet.iter_rows():")
    lines.append(f"{indent}                for cell in row:")
    lines.append(f"{indent}                    if cell.value and isinstance(cell.value, str):")
    lines.append(f"{indent}                        full_text += cell.value + ' '")
    lines.append(f"{indent}    elif template_ext.endswith('.pptx') or template_ext.endswith('.ppt'):")
    lines.append(f"{indent}        from pptx import Presentation")
    lines.append(f"{indent}        prs = Presentation(\"{template_file}\")")
    lines.append(f"{indent}        for slide in prs.slides:")
    lines.append(f"{indent}            for shape in slide.shapes:")
    lines.append(f"{indent}                if shape.has_text_frame:")
    lines.append(f"{indent}                    for p in shape.text_frame.paragraphs:")
    lines.append(f"{indent}                        for run in p.runs:")
    lines.append(f"{indent}                            if run.text:")
    lines.append(f"{indent}                                full_text += run.text + ' '")
    lines.append(f"{indent}    else:")
    lines.append(f"{indent}        with open(\"{template_file}\", \"r\", encoding=\"utf-8\", errors='ignore') as f:")
    lines.append(f"{indent}            full_text = f.read()")
    lines.append(f"{indent}    ")
    lines.append(indent + "    found_keys = re.findall(r'\\{\\{([^}]+)\\}\\}', full_text)")
    lines.append(f"{indent}    for k in found_keys:")
    lines.append(f"{indent}        extracted_keys.add(k.strip())")
    lines.append(f"{indent}    ")
    lines.append(f"{indent}    schema_dict = {{k: '' for k in extracted_keys}}")
    # 예전엔 여기서 빈칸 스키마만 내보내고 직전 노드가 갖고 있던 실제 데이터(예: 자기소개 원문을
    # 분석해서 뽑아낸 이름/경력/지원동기 등)를 그냥 버렸다. 그러면 바로 뒤에서 빈칸을 채우는
    # llmNode는 "어떤 빈칸이 있는지"만 알고 "무엇으로 채워야 할지"는 전혀 모른 채 실행돼서, 실제
    # 내용 대신 그럴듯하게 지어낸 값(홍길동, 서울대학교 등)을 채우거나 아예 빈칸 여러 개를 그냥
    # 건너뛰는 문제가 있었다(사용자가 실제로 겪음 — 자기소개서 hwpx에 {{fullName}} 등이 안 채워진
    # 채로 남아있었음). 빈칸 목록과 함께 실제 데이터도 그대로 실어 보내서, 뒤에 오는 프롬프트/LLM이
    # 둘 다 보고 채우게 한다.
    lines.append(f"{indent}    _tmpl_incoming_{node_id} = {prev_res_var if prev_res_var else 'last_result'}")
    lines.append(f"{indent}    res_val_{node_id} = '[채워야 할 빈칸 목록]:\\n' + json.dumps(schema_dict, ensure_ascii=False, indent=2) + '\\n\\n[사용 가능한 실제 데이터]:\\n' + str(_tmpl_incoming_{node_id})")
    lines.append(f"{indent}except Exception as e:")
    lines.append(f"{indent}    res_val_{node_id} = f'Error analyzing template: {{str(e)}}'")
    lines.append(f"{indent}last_result = res_val_{node_id}")
    
    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_val_{node_id}", visited=visited)


@node_registry.register('fileModifierNode')
def generate_file_modifier_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Auto Fill Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    template_file = node.get('data', {}).get('template_path', '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\\', '/')
    # output_file과 동일하게 uploads/ 밑으로 정규화한다 — 안 그러면 챗봇이 지어낸 "자기소개서_템플릿.hwpx"
    # 처럼 디렉터리 없는 경로가 서버 실행 위치(backend/) 바로 밑에 그대로 생겨 uploads/ 밖에 파일이
    # 흩어지는 문제가 있었다(실제로 backend/ 루트에 파일이 생기는 것을 확인함).
    template_file = _confine_to_uploads(template_file)
                    
    output_file = node.get('data', {}).get('output_path', '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    if not output_file:
        # output_path를 안 정해주면 예전엔 항상 "output.확장자"로 저장돼서, 다운로드한 파일
        # 이름이 무슨 내용인지 알 수 없고, 서로 다른 실행이 같은 이름을 덮어쓸 위험도 있었다.
        # template_path의 제목(있으면)을 따서 이름을 짓고, 실행마다 겹치지 않게 짧은 임의
        # 문자열을 붙인다. compile_workflow는 실행할 때마다 새로 호출되므로(graph.py 참고)
        # 이 uuid는 매 실행마다 새로 생성된다.
        unique_suffix = uuid.uuid4().hex[:6]
        if template_file:
            ext = template_file.split('.')[-1]
            base_title = os.path.splitext(os.path.basename(template_file))[0]
            base_title = base_title.replace('_템플릿', '').replace('_template', '').replace('_Template', '')
            base_title = base_title.strip() or '결과'
            output_file = f"{base_title}_결과_{unique_suffix}.{ext}"
        else:
            output_file = f"결과_{unique_suffix}.txt"

    output_file = _confine_to_uploads(output_file)
    lines.append(f"{indent}try:")
    lines.append(f"{indent}    import json")
    lines.append(f"{indent}    import os")
    lines.append(f"{indent}    data_in = {prev_res_var if prev_res_var else 'last_result'}")
    lines.append(f"{indent}    if isinstance(data_in, str):")
    lines.append(f"{indent}        try:")
    lines.append(f"{indent}            data_dict = json.loads(_strip_json_fence(data_in))")
    lines.append(f"{indent}        except: data_dict = {{}}")
    lines.append(f"{indent}    elif isinstance(data_in, dict):")
    lines.append(f"{indent}        data_dict = data_in")
    lines.append(f"{indent}    else:")
    lines.append(f"{indent}        data_dict = {{}}")
    lines.append(f"{indent}    ")
    lines.append(f"{indent}    template_ext = \"{template_file}\".lower()")
    lines.append(f"{indent}    output_ext = \"{output_file}\".lower()")
    # PDF는 hwpx/docx처럼 "빈칸 있는 서식 파일을 나중에 찾아 바꾸는" 방식이 안 맞는 포맷이라
    # (텍스트 스트림을 안전하게 찾아 바꾸기 어려움) 아예 템플릿 개념을 안 쓰고, data_dict를 바로
    # 새 PDF 문서로 렌더링해서 만든다 — output_path가 .pdf면 template_path는 아예 무시한다.
    lines.append(f"{indent}    if output_ext.endswith('.pdf'):")
    lines.append(f"{indent}        from template_generator import render_pdf_document")
    lines.append(f"{indent}        _pdf_title_{node_id} = os.path.splitext(os.path.basename(\"{output_file}\"))[0]")
    lines.append(f"{indent}        render_pdf_document(\"{output_file}\", data_dict, title=_pdf_title_{node_id})")
    lines.append(f"{indent}        res_text_{node_id} = \"{output_file}\"")
    lines.append(f"{indent}    else:")
    # 챗봇이 지어낸 template_path가 실제로 업로드된 적 없어 파일이 없는 경우, 지금 채우려는
    # 진짜 값(data_dict의 키)을 그대로 필드로 써서 즉석에서 빈 템플릿을 만들고 이어서 채운다.
    # (templateAnalyzerNode와 달리 여기선 이미 실제 값이 있으니 LLM으로 필드명을 추측할 필요가 없다.)
    lines.append(f"{indent}        _fm_needs_regen_{node_id} = not os.path.exists(\"{template_file}\")")
    # 파일이 이미 있는데 그 안의 {{key}}가 지금 채우려는 data_dict 키와 절반도 안 겹치는 경우가
    # 있다. 예전에는 "낡은 템플릿"으로 보고 그 자리에 새로 만들었는데, 그 대상이 사용자가 올린
    # 서식일 수도 있었다(generate_hwpx_template 이 템플릿 경로에 직접 쓴다). 지금은 덮어쓰지 않고
    # **실패시킨다** — 무엇이 있고 무엇이 없는지 알려주면 사용자가 서식이나 스키마를 고칠 수 있다.
    # hwpx 는 이 사전 점검을 하지 않는다 — `extract_template_keys` 가 run 분할을 모르는 옛 방식이라
    # 쪼개진 서식을 "키가 안 맞는다"고 잘못 막는다. 공용 엔진이 채운 뒤 정확히 보고한다.
    lines.append(f"{indent}        if not _fm_needs_regen_{node_id} and template_ext.endswith('.docx') and data_dict:")
    lines.append(f"{indent}            from template_generator import extract_template_keys")
    lines.append(f"{indent}            _fm_existing_keys_{node_id} = extract_template_keys(\"{template_file}\")")
    lines.append(f"{indent}            _fm_wanted_keys_{node_id} = set(data_dict.keys())")
    lines.append(f"{indent}            _fm_overlap_{node_id} = _fm_existing_keys_{node_id} & _fm_wanted_keys_{node_id}")
    lines.append(f"{indent}            if not _fm_existing_keys_{node_id} or len(_fm_overlap_{node_id}) < (len(_fm_wanted_keys_{node_id}) + 1) // 2:")
    lines.append(f"{indent}                raise ValueError(")
    lines.append(f"{indent}                    '서식 파일의 빈칸 이름이 채우려는 값과 맞지 않습니다: ' + \"{template_file}\"")
    lines.append(f"{indent}                    + ' / 서식에 있는 빈칸: ' + (', '.join(sorted(_fm_existing_keys_{node_id})) or '(없음)')")
    lines.append(f"{indent}                    + ' / 채우려는 값: ' + (', '.join(sorted(_fm_wanted_keys_{node_id})) or '(없음)')")
    lines.append(f"{indent}                    + ' — 서식의 {{{{빈칸}}}} 이름을 값의 키와 맞추거나, 서식 파일을 다시 선택해주세요.'")
    lines.append(f"{indent}                )")
    lines.append(f"{indent}        if _fm_needs_regen_{node_id} and (template_ext.endswith('.hwpx') or template_ext.endswith('.docx')) and data_dict:")
    lines.append(f"{indent}            from template_generator import generate_hwpx_template, generate_docx_template")
    lines.append(f"{indent}            _fm_title_{node_id} = os.path.splitext(os.path.basename(\"{template_file}\"))[0].replace('_템플릿', '').replace('_template', '')")
    lines.append(f"{indent}            if template_ext.endswith('.hwpx'):")
    lines.append(f"{indent}                generate_hwpx_template(\"{template_file}\", list(data_dict.keys()), title=_fm_title_{node_id})")
    lines.append(f"{indent}            else:")
    lines.append(f"{indent}                generate_docx_template(\"{template_file}\", list(data_dict.keys()), title=_fm_title_{node_id})")
    lines.append(f"{indent}        if template_ext.endswith('.hwp'):")
    lines.append(f"{indent}            raise ValueError('HWP(.hwp) 서식 파일은 현재 지원하지 않습니다. HWPX(.hwpx)나 Word(.docx) 서식을 사용해주세요.')")
    # HWPX 채우기는 공용 엔진이 한다(documents/hwpx). 여기 있던 문자열 치환은 run 이 쪼개진
    # 자리표시자를 못 찾았고, 재압축이 mimetype 의 STORED 규칙을 깼으며, 손으로 만든 XML escape
    # 가 이중 이스케이프를 냈다. 셋 다 엔진 쪽에서 테스트로 고정돼 있다.
    lines.append(f"{indent}        elif template_ext.endswith('.hwpx'):")
    lines.append(f"{indent}            from documents import hwpx as _hwpx_engine")
    lines.append(f"{indent}            _fm_fill_{node_id} = _hwpx_engine.fill_template(")
    lines.append(f"{indent}                \"{template_file}\", data_dict, \"{output_file}\")")
    lines.append(f"{indent}            if _fm_fill_{node_id}.unresolved:")
    # §3.6 — 미치환 자리표시자는 결과에 명시하고 기본 설정에서는 실패로 다룬다.
    lines.append(f"{indent}                raise ValueError(")
    lines.append(f"{indent}                    '서식에 채우지 못한 빈칸이 있습니다: '")
    lines.append(f"{indent}                    + ', '.join(_fm_fill_{node_id}.unresolved)")
    lines.append(f"{indent}                    + ' / 받은 값: ' + (', '.join(sorted(data_dict)) or '(없음)')")
    lines.append(f"{indent}                )")
    lines.append(f"{indent}        elif template_ext.endswith('.docx') or template_ext.endswith('.doc'):")
    lines.append(f"{indent}            from docx import Document as _DocxDocument")
    lines.append(f"{indent}            _docx_doc = _DocxDocument(\"{template_file}\")")
    lines.append(f"{indent}            for p in _docx_doc.paragraphs:")
    lines.append(f"{indent}                for run in p.runs:")
    lines.append(f"{indent}                    for k, v in data_dict.items():")
    lines.append(f"{indent}                        if '{{{{' + str(k) + '}}}}' in run.text:")
    lines.append(f"{indent}                            run.text = run.text.replace('{{{{' + str(k) + '}}}}', str(v))")
    lines.append(f"{indent}            for _tbl in _docx_doc.tables:")
    lines.append(f"{indent}                for _row in _tbl.rows:")
    lines.append(f"{indent}                    for _cell in _row.cells:")
    lines.append(f"{indent}                        for _p in _cell.paragraphs:")
    lines.append(f"{indent}                            for run in _p.runs:")
    lines.append(f"{indent}                                for k, v in data_dict.items():")
    lines.append(f"{indent}                                    if '{{{{' + str(k) + '}}}}' in run.text:")
    lines.append(f"{indent}                                        run.text = run.text.replace('{{{{' + str(k) + '}}}}', str(v))")
    lines.append(f"{indent}            _docx_doc.save(\"{output_file}\")")
    lines.append(f"{indent}        elif template_ext.endswith('.xlsx') or template_ext.endswith('.xls'):")
    lines.append(f"{indent}            import openpyxl")
    lines.append(f"{indent}            wb = openpyxl.load_workbook(\"{template_file}\")")
    lines.append(f"{indent}            for sheet in wb.worksheets:")
    lines.append(f"{indent}                for row in sheet.iter_rows():")
    lines.append(f"{indent}                    for cell in row:")
    lines.append(f"{indent}                        if cell.value and isinstance(cell.value, str):")
    lines.append(f"{indent}                            for k, v in data_dict.items():")
    lines.append(f"{indent}                                if '{{{{' + str(k) + '}}}}' in cell.value:")
    lines.append(f"{indent}                                    cell.value = cell.value.replace('{{{{' + str(k) + '}}}}', str(v))")
    lines.append(f"{indent}            wb.save(\"{output_file}\")")
    lines.append(f"{indent}        elif template_ext.endswith('.pptx') or template_ext.endswith('.ppt'):")
    lines.append(f"{indent}            from pptx import Presentation")
    lines.append(f"{indent}            prs = Presentation(\"{template_file}\")")
    lines.append(f"{indent}            for slide in prs.slides:")
    lines.append(f"{indent}                for shape in slide.shapes:")
    lines.append(f"{indent}                    if shape.has_text_frame:")
    lines.append(f"{indent}                        for p in shape.text_frame.paragraphs:")
    lines.append(f"{indent}                            for run in p.runs:")
    lines.append(f"{indent}                                if run.text:")
    lines.append(f"{indent}                                    for k, v in data_dict.items():")
    lines.append(f"{indent}                                        if '{{{{' + str(k) + '}}}}' in run.text:")
    lines.append(f"{indent}                                            run.text = run.text.replace('{{{{' + str(k) + '}}}}', str(v))")
    lines.append(f"{indent}            prs.save(\"{output_file}\")")
    lines.append(f"{indent}        else:")
    lines.append(f"{indent}            with open(\"{output_file}\", \"w\", encoding=\"utf-8\") as _f:")
    lines.append(f"{indent}                _f.write(str({prev_res_var if prev_res_var else 'last_result'}))")
    lines.append(f"{indent}        res_text_{node_id} = \"{output_file}\"")
    lines.append(f"{indent}    ")
    lines.append(f"{indent}except Exception as e:")
    lines.append(f"{indent}    res_text_{node_id} = f\"Error formatting file: {{str(e)}}\"")
    # 완성한 문서를 artifact 로 등록한다(ADR-0018 FILE-SEND-0 ②) — 이메일·디스코드의 첨부 포트가
    # 이 값을 읽는다. 실패했을 때는 파일이 없으므로 register_generated_file 이 None 을 돌려준다.
    lines.append(f"{indent}import artifacts as _artifacts")
    lines.append(f"{indent}_fm_ref_{node_id} = _artifacts.register_generated_file(")
    lines.append(f"{indent}    db, path=\"{output_file}\", owner_user_id=__owner_user_id__,")
    lines.append(f"{indent}    project_id=kwargs.get('project_id'), purpose='generated-document')")
    lines.append(f"{indent}_record_artifacts('{node_id}', [_fm_ref_{node_id}.to_public_dict()] if _fm_ref_{node_id} else [])")
    lines.append(f"{indent}last_result = res_text_{node_id}")

    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)


@node_registry.register('tokenizerNode')
def generate_tokenizer_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    method = node.get('data', {}).get('method', 'extract_text')
    lines.append(f"{indent}# --- Tokenizer Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")
    lines.append(f"{indent}file_path_raw = {prev_res_var if prev_res_var else 'last_result'}")
    lines.append(f"{indent}import re")
    lines.append(f"{indent}match_{node_id} = re.search(r'\\[Attached File: (.*?)\\]', str(file_path_raw))")
    lines.append(f"{indent}if match_{node_id}:")
    lines.append(f"{indent}    file_path = match_{node_id}.group(1)")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    file_path = str(file_path_raw)")
    # 경로를 업로드 루트 안으로 가둔다(2026-08-31 적대적 리뷰: tokenizer 가 valueNode 가드를
    # 우회해 임의 파일을 읽었다). 루트 밖이면 아래 확장자 분기가 모두 '읽지 못함'으로 떨어지도록
    # 존재할 수 없는 경로로 바꾼다 — open()/read 8곳을 개별로 고치지 않아도 전부 막힌다.
    lines.append(f"{indent}_tok_ok_{node_id} = _safe_user_path(file_path)")
    lines.append(f"{indent}file_path = str(_tok_ok_{node_id}) if _tok_ok_{node_id} is not None else str(_Path(_os.getenv('UPLOAD_DIR','uploads')).resolve() / '__blocked_path__')")
    lines.append(f"{indent}res_text_{node_id} = []")
    
    lines.append(f"{indent}if str(file_path).lower().endswith('.pdf'):")
    lines.append(f"{indent}    import PyPDF2")
    lines.append(f"{indent}    with open(file_path, 'rb') as f:")
    lines.append(f"{indent}        reader = PyPDF2.PdfReader(f)")
    if method == 'chunk_pages':
        lines.append(f"{indent}        res_text_{node_id} = [page.extract_text() for page in reader.pages]")
    else:
        lines.append(f"{indent}        res_text_{node_id} = ['\\n'.join([page.extract_text() for page in reader.pages])]")
        
    lines.append(f"{indent}elif str(file_path).lower().endswith('.xlsx') or str(file_path).lower().endswith('.xls'):")
    lines.append(f"{indent}    import pandas as pd")
    if method == 'chunk_pages':
        lines.append(f"{indent}    df = pd.read_excel(file_path, sheet_name=None)")
        lines.append(f"{indent}    res_text_{node_id} = [f'Sheet: {{sheet}}\\n{{df[sheet].to_string()}}' for sheet in df.keys()]")
    else:
        lines.append(f"{indent}    df = pd.read_excel(file_path)")
        lines.append(f"{indent}    res_text_{node_id} = [df.to_string()]")
        
    lines.append(f"{indent}elif str(file_path).lower().endswith('.pptx'):")
    lines.append(f"{indent}    from pptx import Presentation")
    lines.append(f"{indent}    prs = Presentation(file_path)")
    if method == 'chunk_pages':
        lines.append(f"{indent}    for slide in prs.slides:")
        lines.append(f"{indent}        slide_text = []")
        lines.append(f"{indent}        for shape in slide.shapes:")
        lines.append(f"{indent}            if hasattr(shape, 'text'): slide_text.append(shape.text)")
        lines.append(f"{indent}        res_text_{node_id}.append('\\n'.join(slide_text))")
    else:
        lines.append(f"{indent}    full_text = []")
        lines.append(f"{indent}    for slide in prs.slides:")
        lines.append(f"{indent}        for shape in slide.shapes:")
        lines.append(f"{indent}            if hasattr(shape, 'text'): full_text.append(shape.text)")
        lines.append(f"{indent}    res_text_{node_id} = ['\\n'.join(full_text)]")

    lines.append(f"{indent}elif str(file_path).lower().endswith('.hwp'):")
    lines.append(f"{indent}    try:")
    lines.append(f"{indent}        import olefile")
    lines.append(f"{indent}        import zlib")
    lines.append(f"{indent}        import struct")
    lines.append(f"{indent}        f = olefile.OleFileIO(file_path)")
    lines.append(f"{indent}        dirs = f.listdir()")
    lines.append(f"{indent}        if ['PrvText'] in dirs:")
    lines.append(f"{indent}            text = f.openstream('PrvText').read().decode('utf-16le')")
    lines.append(f"{indent}            res_text_{node_id} = [text]")
    lines.append(f"{indent}        else:")
    lines.append(f"{indent}            body_dirs = [d for d in dirs if d[0] == 'BodyText']")
    lines.append(f"{indent}            text = ''")
    lines.append(f"{indent}            for d in body_dirs:")
    lines.append(f"{indent}                unpacked_data = zlib.decompress(f.openstream(d).read(), -15)")
    lines.append(f"{indent}                i = 0")
    lines.append(f"{indent}                while i < len(unpacked_data):")
    lines.append(f"{indent}                    header = struct.unpack_from('<I', unpacked_data, i)[0]")
    lines.append(f"{indent}                    tag_id = header & 0x3FF")
    lines.append(f"{indent}                    size = (header >> 20) & 0xFFF")
    lines.append(f"{indent}                    if size == 0xFFF:")
    lines.append(f"{indent}                        size = struct.unpack_from('<I', unpacked_data, i + 4)[0]")
    lines.append(f"{indent}                        i += 8")
    lines.append(f"{indent}                    else:")
    lines.append(f"{indent}                        i += 4")
    lines.append(f"{indent}                    if tag_id == 67:")
    lines.append(f"{indent}                        try:")
    lines.append(f"{indent}                            decoded = unpacked_data[i:i+size].decode('utf-16le')")
    lines.append(f"{indent}                            text += ''.join(c for c in decoded if ord(c) >= 32 or c in '\\n\\r\\t') + '\\n'")
    lines.append(f"{indent}                        except: pass")
    lines.append(f"{indent}                    i += size")
    lines.append(f"{indent}            if text.strip():")
    lines.append(f"{indent}                res_text_{node_id} = [text]")
    lines.append(f"{indent}            else:")
    lines.append(f"{indent}                import subprocess")
    lines.append(f"{indent}                res = subprocess.run(['hwp5txt', file_path], capture_output=True, text=True, encoding='utf-8')")
    lines.append(f"{indent}                res_text_{node_id} = [res.stdout] if res.stdout else ['[Error or empty: hwp5txt]']")
    lines.append(f"{indent}    except Exception as e:")
    lines.append(f"{indent}        res_text_{node_id} = [str(e)]")

    lines.append(f"{indent}elif str(file_path).lower().endswith('.hwpx'):")
    lines.append(f"{indent}    import zipfile")
    lines.append(f"{indent}    import xml.etree.ElementTree as ET")
    lines.append(f"{indent}    try:")
    lines.append(f"{indent}        with zipfile.ZipFile(file_path, 'r') as zf:")
    lines.append(f"{indent}            sec_files = [f for f in zf.namelist() if f.startswith('Contents/section') and f.endswith('.xml')]")
    lines.append(f"{indent}            hwpx_text = []")
    lines.append(f"{indent}            for sec in sorted(sec_files):")
    lines.append(f"{indent}                root = ET.fromstring(zf.read(sec))")
    lines.append(f"{indent}                for elem in root.iter():")
    lines.append(f"{indent}                    if elem.tag.endswith('}}t') or elem.tag.endswith(':t'):")
    lines.append(f"{indent}                        if elem.text: hwpx_text.append(elem.text)")
    lines.append(f"{indent}                hwpx_text.append('\\n')")
    lines.append(f"{indent}            res_text_{node_id} = [''.join(hwpx_text)]")
    lines.append(f"{indent}    except Exception as e:")
    lines.append(f"{indent}        res_text_{node_id} = [str(e)]")
    
    lines.append(f"{indent}elif str(file_path).lower().endswith(('.txt', '.csv', '.md', '.json', '.html')):")
    lines.append(f"{indent}    try:")
    lines.append(f"{indent}        with open(file_path, 'r', encoding='utf-8') as f:")
    lines.append(f"{indent}            res_text_{node_id} = [f.read()]")
    lines.append(f"{indent}    except Exception as e:")
    lines.append(f"{indent}        res_text_{node_id} = [f'Text Read Error: {{str(e)}}']")

    lines.append(f"{indent}if res_text_{node_id}:")
    lines.append(f"{indent}    parsed_str_{node_id} = '\\n'.join(res_text_{node_id})")
    lines.append(f"{indent}    if match_{node_id}:")
    lines.append(f"{indent}        parsed_output_{node_id} = str(file_path_raw).replace(match_{node_id}.group(0), f'[Parsed Content:]\\n{{parsed_str_{node_id}}}\\n')")
    lines.append(f"{indent}    else:")
    lines.append(f"{indent}        parsed_output_{node_id} = parsed_str_{node_id}")
    lines.append(f"{indent}else:")
    lines.append(f"{indent}    parsed_output_{node_id} = str(file_path_raw)")
    lines.append(f"{indent}last_result = parsed_output_{node_id}")

    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        # 예전엔 여기서 res_text_{node_id}(파싱 실패 시 빈 리스트 [])를 그대로 넘겨서, str([])=='[]'가
        # 하류 conditionNode의 "결과가 빈 문자열인지" 검사를 절대 통과하지 못하게 막는 버그가 있었다.
        # 실제로 계산된 최종 문자열(parsed_output_{node_id})을 넘긴다.
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"parsed_output_{node_id}", visited=visited)


@node_registry.register('posterGeneratorNode')
def generate_poster_generator_node(node_id, node, indent, active_llm_id, prev_res_var, visited, node_dict, forward_edges, incoming_edges, lines, generate_block_fn):
    lines.append(f"{indent}# --- Poster Generator Node ({node_id}) ---")
    lines.append(f"{indent}_start_{node_id} = datetime.datetime.utcnow().isoformat()")

    data = node.get('data', {})
    fmt = data.get('outputFormat', 'png')
    if fmt not in ('png', 'pdf'):
        fmt = 'png'
    try:
        width = int(data.get('width', 900))
    except (TypeError, ValueError):
        width = 900
    try:
        height = int(data.get('height', 1200))
    except (TypeError, ValueError):
        height = 1200
    background_preset = data.get('backgroundPreset', 'none')
    if background_preset not in {
        'none',
        'poster-01-midnight-grid', 'poster-02-cobalt-orbits', 'poster-03-violet-arches',
        'poster-04-emerald-flow', 'poster-05-layered-paper', 'poster-06-dot-matrix',
        'poster-07-blueprint-lines', 'poster-08-diagonal-blocks', 'poster-09-emerald-wave',
        'poster-10-neutral-editorial', 'poster-11-concentric-frames', 'poster-12-sparse-geometry',
    }:
        background_preset = 'none'

    output_file = data.get('output_path', '').replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    if not output_file:
        unique_suffix = uuid.uuid4().hex[:6]
        output_file = f"poster_{unique_suffix}.{fmt}"
    output_file = _confine_to_uploads(output_file)

    lines.append(f"{indent}try:")
    lines.append(f"{indent}    from poster_generator import render_html_to_file")
    lines.append(f"{indent}    _poster_html_{node_id} = str({prev_res_var if prev_res_var else 'last_result'})")
    lines.append(f"{indent}    render_html_to_file(_poster_html_{node_id}, \"{output_file}\", width={width}, height={height}, fmt=\"{fmt}\", background_preset=\"{background_preset}\")")
    lines.append(f"{indent}    res_text_{node_id} = \"{output_file}\"")
    # 렌더한 포스터를 artifact 로 등록한다(ADR-0018 FILE-SEND-0 ②). 등록해야 소유자·만료가
    # 생기고, 발송 노드가 경로 문자열을 추측하지 않고 첨부할 수 있다.
    lines.append(f"{indent}    import artifacts as _artifacts")
    lines.append(f"{indent}    _poster_ref_{node_id} = _artifacts.register_generated_file(")
    lines.append(f"{indent}        db, path=\"{output_file}\", owner_user_id=__owner_user_id__,")
    lines.append(f"{indent}        project_id=kwargs.get('project_id'), purpose='generated-poster')")
    lines.append(f"{indent}    _record_artifacts('{node_id}', [_poster_ref_{node_id}.to_public_dict()] if _poster_ref_{node_id} else [])")
    lines.append(f"{indent}except Exception as e:")
    lines.append(f"{indent}    res_text_{node_id} = f\"Error generating poster: {{str(e)}}\"")
    lines.append(f"{indent}last_result = res_text_{node_id}")

    lines.append(f"{indent}log_step('{node_id}', '{node['type']}', _start_{node_id}, result=last_result)")
    next_edges = forward_edges.get(node_id, [])
    for target_id, handle in next_edges:
        generate_block_fn(target_id, indent, active_llm_id=active_llm_id, prev_res_var=f"res_text_{node_id}", visited=visited)
