import re

with open('frontend/src/customNodes.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = {
    ' Start</div>': ' 시작</div>',
    ' Prompt Node</div>': ' 프롬프트</div>',
    ' LLM Node</div>': ' LLM Node</div>',
    ' Value Node</div>': ' 변수 (값)</div>',
    ' Python Node</div>': ' 파이썬</div>',
    ' Condition Node</div>': ' 조건 분기</div>',
    ' Output Node</div>': ' 결과 출력</div>',
    ' Tokenizer</div>': ' 토크나이저</div>',
    ' Distributor</div>': ' 분배기</div>',
    ' Auto Fill Node</div>': ' 자동 완성</div>',
    ' Template Analyzer</div>': ' 템플릿 분석</div>',
    ' Loop Node</div>': ' 반복 (Loop)</div>',
    ' Break Node</div>': ' 반복 종료</div>',
    '<p style={{ margin: 0, fontSize: \'0.85rem\', color: \'#cbd5e1\' }}>Entry Point</p>': '<p style={{ margin: 0, fontSize: \'0.85rem\', color: \'#cbd5e1\' }}>시작점</p>',
    '<label>User Prompt</label>': '<label>사용자 프롬프트</label>',
    'placeholder="Enter user prompt..."': 'placeholder="프롬프트를 입력하세요..."',
    '<label>Model</label>': '<label>AI 모델</label>',
    '<label>Value</label>': '<label>값</label>',
    'placeholder="Enter value"': 'placeholder="값을 입력하세요"',
    '<label>Python Code</label>': '<label>파이썬 코드</label>',
    '<label>Condition</label>': '<label>조건식</label>',
    'placeholder="e.g. data == \'yes\'"': 'placeholder="예: data == \'yes\'"',
    '<label>Format</label>': '<label>출력 형식</label>',
    '<label>Delimiter</label>': '<label>구분자</label>',
    '<label>Distribute by</label>': '<label>분배 기준</label>',
    '<label>Template</label>': '<label>템플릿</label>',
    '<label>List to iterate</label>': '<label>반복 대상 리스트</label>',
    '<label>Condition to Break</label>': '<label>종료 조건식</label>',
    '<label>System Prompt (Optional)</label>': '<label>시스템 프롬프트 (선택)</label>'
}

for k, v in replacements.items():
    content = content.replace(k, v)

with open('frontend/src/customNodes.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Translation of customNodes.jsx complete.")
