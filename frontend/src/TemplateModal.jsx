import React, { useState, useEffect } from 'react';
import { Save, Folder, X, Play, Info } from 'lucide-react';
import './TemplateModal.css';

const BUILT_IN_TEMPLATES = [
  {
    id: 'builtin-1',
    name: '📝 문서 자동 채우기 (이력서)',
    description: '비정형 텍스트에서 데이터를 추출하여 HWP/Excel/PPT 템플릿을 자동으로 채웁니다.',
    usage: '1. "템플릿 분석기" 노드에서 사용할 문서 파일(.hwp, .docx 등)을 업로드하세요.\n2. "지원자 정보" 노드에 처리할 비정형 텍스트를 입력하세요.\n3. [Deploy] 버튼을 눌러 실행 결과를 확인하세요.',
    url: 'https://github.com/your-repo/docs/template-filling',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_1', type: 'templateAnalyzerNode', position: { x: 300, y: 150 }, data: { label: '템플릿 분석기', template_path: 'C:\\Users\\kimchunsik\\Desktop\\업무자동화 비주얼화\\backend\\uploads\\입사 지원서 .hwp', filename: '입사 지원서 .hwp' } },
        { id: 'node_info', type: 'valueNode', position: { x: 550, y: 150 }, data: { label: '지원자 정보', value: '홍길동은 네이버에서 3년간 마케팅 기획자로 일했습니다. 연락처는 010-1234-5678이며 마케팅 팀에 지원합니다.' } },
        { id: 'node_2', type: 'promptNode', position: { x: 850, y: 150 }, data: { label: '프롬프트', userPrompt: '다음 JSON 형식(keys)에 맞게 텍스트에서 정보를 추출해 줘. 반드시 JSON 형식으로만 대답해.' } },
        { id: 'node_3', type: 'llmNode', position: { x: 1200, y: 150 }, data: { label: 'LLM', model: 'gemini-3.5-flash', systemPrompt: '당신은 정확한 데이터 추출 어시스턴트입니다.' } },
        { id: 'node_4', type: 'fileModifierNode', position: { x: 1550, y: 150 }, data: { label: '자동 채우기', template_path: 'C:\\Users\\kimchunsik\\Desktop\\업무자동화 비주얼화\\backend\\uploads\\입사 지원서 .hwp', filename: '입사 지원서 .hwp', output_path: 'output_filled.hwp' } }
      ],
      edges: [
        { id: 'e_start-1', source: 'node_start', target: 'node_1', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e1-info', source: 'node_1', target: 'node_info', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_info-2', source: 'node_info', target: 'node_2', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e2-3', source: 'node_2', target: 'node_3', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e3-4', source: 'node_3', target: 'node_4', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-2',
    name: '🌐 단순 번역 파이프라인',
    description: '입력 텍스트를 다른 언어로 번역하는 기본적인 파이프라인입니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_1', type: 'valueNode', position: { x: 300, y: 150 }, data: { label: '입력값', value: 'Hello, how are you?' } },
        { id: 'node_2', type: 'llmNode', position: { x: 650, y: 150 }, data: { label: 'LLM', model: 'gpt-4o-mini', systemPrompt: '당신은 전문 번역가입니다. 주어진 텍스트를 한국어로 번역하세요.' } },
        { id: 'node_3', type: 'outputNode', position: { x: 1000, y: 150 }, data: { label: '결과 출력' } }
      ],
      edges: [
        { id: 'e_start-1', source: 'node_start', target: 'node_1', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e1-2', source: 'node_1', target: 'node_2', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e2-3', source: 'node_2', target: 'node_3', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-3',
    name: '🤖 동적 챗봇 템플릿',
    description: '동적 입력 노드와 LLM을 사용하여 반응형 챗봇을 만드는 템플릿입니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_dyn', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: '동적 입력', inputLabel: '무엇이든 물어보세요!' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 650, y: 150 }, data: { label: 'LLM', model: 'gemini-3.5-flash', systemPrompt: '당신은 친절한 AI 어시스턴트입니다. 사용자의 질문에 답해주세요.' } },
        { id: 'node_out', type: 'kakaoNode', position: { x: 1000, y: 150 }, data: { label: '카카오 알림톡', receiver: '기본 사용자' } }
      ],
      edges: [
        { id: 'e_start-dyn', source: 'node_start', target: 'node_dyn', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_dyn-llm', source: 'node_dyn', target: 'node_llm', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_llm-out', source: 'node_llm', target: 'node_out', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-4',
    name: '📰 동적 뉴스 요약기',
    description: '뉴스 기사의 URL을 입력하면 웹을 크롤링하고, 3줄로 요약한 후 이메일로 전송합니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_url', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: '뉴스 URL 입력', inputLabel: '요약할 기사 URL을 입력하세요' } },
        { id: 'node_crawl', type: 'webCrawlerNode', position: { x: 550, y: 150 }, data: { label: '웹 크롤러', url: '' } },
        { id: 'node_prompt', type: 'promptNode', position: { x: 850, y: 150 }, data: { label: '요약 프롬프트', userPrompt: '다음 텍스트를 읽고 핵심 내용을 3줄로 요약해줘.' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 1150, y: 150 }, data: { label: 'LLM', model: 'gemini-3.5-flash', systemPrompt: '당신은 정확하고 빠른 뉴스 요약 전문가입니다.' } },
        { id: 'node_email', type: 'emailNode', position: { x: 1450, y: 150 }, data: { label: '이메일 전송', toEmail: 'boss@company.com' } }
      ],
      edges: [
        { id: 'e_s-u', source: 'node_start', target: 'node_url', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_u-c', source: 'node_url', target: 'node_crawl', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_c-p', source: 'node_crawl', target: 'node_prompt', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_p-l', source: 'node_prompt', target: 'node_llm', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_l-e', source: 'node_llm', target: 'node_email', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-5',
    name: '❓ 조건부 자동 응답기',
    description: '고객 메시지를 분류합니다. 불만 접수면 매니저에게 카카오톡 알림을, 일반 문의면 LLM이 답변합니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 250 }, data: { label: '시작' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 250 }, data: { label: '고객 메시지', inputLabel: '고객 문의 내용' } },
        { id: 'node_class', type: 'llmNode', position: { x: 600, y: 250 }, data: { label: '분류기 LLM', model: 'gpt-4o-mini', systemPrompt: '고객 문의를 분석하여, 불만/환불 요청이면 "COMPLAINT", 단순 문의면 "NORMAL"이라고만 대답해라.' } },
        { id: 'node_cond', type: 'conditionNode', position: { x: 900, y: 250 }, data: { label: '불만 여부 확인', condition: 'Contains', value: 'COMPLAINT' } },
        { id: 'node_kakao', type: 'kakaoNode', position: { x: 1250, y: 100 }, data: { label: '담당자 알림 (카카오톡)', receiver: 'CS 담당자' } },
        { id: 'node_reply', type: 'llmNode', position: { x: 1250, y: 400 }, data: { label: '자동 답변 LLM', model: 'gemini-3.5-flash', systemPrompt: '고객의 질문에 친절하게 답변하는 CS 봇입니다.' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1600, y: 400 }, data: { label: '최종 답변 출력' } }
      ],
      edges: [
        { id: 'e_s-i', source: 'node_start', target: 'node_in', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_i-c', source: 'node_in', target: 'node_class', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_c-co', source: 'node_class', target: 'node_cond', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_cond-k', source: 'node_cond', target: 'node_kakao', sourceHandle: 'true', targetHandle: 'in' },
        { id: 'e_cond-r', source: 'node_cond', target: 'node_reply', sourceHandle: 'false', targetHandle: 'in' },
        { id: 'e_r-o', source: 'node_reply', target: 'node_out', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_i-r', source: 'node_in', target: 'node_reply', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-6',
    name: '🌐 API 데이터 가져오기',
    description: '공개 API에서 데이터를 가져오고 특정 키의 값을 추출합니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_http', type: 'httpRequestNode', position: { x: 300, y: 150 }, data: { label: 'API 호출', method: 'GET', url: 'https://jsonplaceholder.typicode.com/todos/1' } },
        { id: 'node_parse', type: 'jsonParserNode', position: { x: 600, y: 150 }, data: { label: 'JSON 파싱', mode: 'parse' } },
        { id: 'node_extract', type: 'jsonParserNode', position: { x: 900, y: 150 }, data: { label: 'Title 추출', mode: 'extract', extractKey: 'title' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1200, y: 150 }, data: { label: '결과값' } }
      ],
      edges: [
        { id: 'e_s-h', source: 'node_start', target: 'node_http', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_h-p', source: 'node_http', target: 'node_parse', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_p-e', source: 'node_parse', target: 'node_extract', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_e-o', source: 'node_extract', target: 'node_out', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-7',
    name: '💬 웹훅 알리미',
    description: '동적 입력을 받아 슬랙이나 디스코드 같은 웹훅으로 전송합니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: '입력 메시지', inputLabel: '알림 보낼 메시지' } },
        { id: 'node_format', type: 'pythonNode', position: { x: 550, y: 150 }, data: { label: '페이로드 포맷팅', code: 'import json\noutput_data = json.dumps({"content": str(input_data)})' } },
        { id: 'node_http', type: 'httpRequestNode', position: { x: 800, y: 150 }, data: { label: '웹훅 POST', method: 'POST', url: 'https://httpbin.org/post', headers: '{"Content-Type": "application/json"}' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1100, y: 150 }, data: { label: '결과 출력' } }
      ],
      edges: [
        { id: 'e_s-i', source: 'node_start', target: 'node_in', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_i-f', source: 'node_in', target: 'node_format', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_f-h', source: 'node_format', target: 'node_http', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_h-o', source: 'node_http', target: 'node_out', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-8',
    name: '🔗 다중 소스 병합',
    description: '두 개의 다른 동적 입력을 하나의 배열로 병합한 뒤 분석합니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 200 }, data: { label: '시작' } },
        { id: 'node_in1', type: 'dynamicInputNode', position: { x: 300, y: 100 }, data: { label: '소스 A', inputLabel: '제품 A 스펙' } },
        { id: 'node_in2', type: 'dynamicInputNode', position: { x: 300, y: 300 }, data: { label: '소스 B', inputLabel: '제품 B 스펙' } },
        { id: 'node_merge', type: 'mergeNode', position: { x: 600, y: 200 }, data: { label: '데이터 병합', mergeStrategy: 'join_newline' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 900, y: 200 }, data: { label: 'LLM 비교 분석', model: 'gpt-4o-mini', systemPrompt: '두 제품의 스펙을 비교하고 장단점을 분석해주세요.' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1200, y: 200 }, data: { label: '출력' } }
      ],
      edges: [
        { id: 'e_s-1', source: 'node_start', target: 'node_in1', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_s-2', source: 'node_start', target: 'node_in2', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_1-m', source: 'node_in1', target: 'node_merge', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_2-m', source: 'node_in2', target: 'node_merge', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_m-l', source: 'node_merge', target: 'node_llm', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_l-o', source: 'node_llm', target: 'node_out', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-9',
    name: '📝 승인 기반 자동 발행',
    description: '초안을 작성하면 LLM이 교정하고, 담당자의 승인을 거쳐 최종 발행합니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: '초안 입력', inputLabel: '초안 작성' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 600, y: 150 }, data: { label: 'LLM 교정기', model: 'gemini-3.5-flash', systemPrompt: '주어진 초안의 맞춤법을 교정하고 전문가처럼 윤문해줘.' } },
        { id: 'node_approval', type: 'humanApprovalNode', position: { x: 900, y: 150 }, data: { label: '담당자 승인', message: '교정된 글을 발행하시겠습니까?' } },
        { id: 'node_publish', type: 'httpRequestNode', position: { x: 1200, y: 150 }, data: { label: '발행 (웹훅)', method: 'POST', url: 'https://httpbin.org/post' } }
      ],
      edges: [
        { id: 'e_s-i', source: 'node_start', target: 'node_in', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_i-l', source: 'node_in', target: 'node_llm', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_l-a', source: 'node_llm', target: 'node_approval', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_a-p', source: 'node_approval', target: 'node_publish', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-10',
    name: '🚨 서버 상태 경고 알림',
    description: '서버 상태를 확인하고, 200 OK가 아니면 카카오 알림톡을 전송합니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 200 }, data: { label: '시작' } },
        { id: 'node_http', type: 'httpRequestNode', position: { x: 300, y: 200 }, data: { label: '서버 핑 (Ping)', method: 'GET', url: 'https://httpbin.org/status/500' } },
        { id: 'node_cond', type: 'conditionNode', position: { x: 600, y: 200 }, data: { label: '500 에러인가?', condition: 'Contains', value: '500' } },
        { id: 'node_alert', type: 'kakaoNode', position: { x: 900, y: 100 }, data: { label: '관리자 알림', receiver: '관리자' } },
        { id: 'node_out', type: 'outputNode', position: { x: 900, y: 300 }, data: { label: '정상 처리됨' } }
      ],
      edges: [
        { id: 'e_s-h', source: 'node_start', target: 'node_http', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_h-c', source: 'node_http', target: 'node_cond', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_c-a', source: 'node_cond', target: 'node_alert', sourceHandle: 'true', targetHandle: 'in' },
        { id: 'e_c-o', source: 'node_cond', target: 'node_out', sourceHandle: 'false', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-11',
    name: '📊 고객 피드백 감정 분석',
    description: 'DB에서 피드백을 가져와 감정을 분석하고, 부정적일 경우 알림을 보냅니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_db', type: 'databaseNode', position: { x: 300, y: 150 }, data: { label: '피드백 가져오기', connectionString: 'sqlite:///feedbacks.db', query: 'SELECT content FROM feedback LIMIT 1;' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 600, y: 150 }, data: { label: '감정 분석 LLM', model: 'gpt-4o-mini', systemPrompt: '감정을 분석하여 반드시 "NEGATIVE" 또는 "POSITIVE" 라고만 답변하세요.' } },
        { id: 'node_cond', type: 'conditionNode', position: { x: 900, y: 150 }, data: { label: '부정적인가?', condition: 'Contains', value: 'NEGATIVE' } },
        { id: 'node_kakao', type: 'kakaoNode', position: { x: 1200, y: 50 }, data: { label: '담당자 알림', receiver: '매니저' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1200, y: 250 }, data: { label: '조치 필요 없음' } }
      ],
      edges: [
        { id: 'e_s-d', source: 'node_start', target: 'node_db', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_d-l', source: 'node_db', target: 'node_llm', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_l-c', source: 'node_llm', target: 'node_cond', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_c-k', source: 'node_cond', target: 'node_kakao', sourceHandle: 'true', targetHandle: 'in' },
        { id: 'e_c-o', source: 'node_cond', target: 'node_out', sourceHandle: 'false', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-12',
    name: '📈 자동화된 SEO 리포트',
    description: '경쟁사 사이트를 크롤링하여 키워드를 분석하고, 결과 리포트를 이메일로 전송합니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_crawl', type: 'webCrawlerNode', position: { x: 300, y: 150 }, data: { label: '사이트 크롤링', url: 'https://example.com' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 600, y: 150 }, data: { label: 'SEO 분석기', model: 'gpt-4o-mini', systemPrompt: '텍스트를 분석하여 상위 5개의 SEO 키워드를 추출하세요.' } },
        { id: 'node_email', type: 'emailNode', position: { x: 900, y: 150 }, data: { label: '리포트 전송', toEmail: 'marketing@example.com' } }
      ],
      edges: [
        { id: 'e_s-c', source: 'node_start', target: 'node_crawl', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_c-l', source: 'node_crawl', target: 'node_llm', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_l-e', source: 'node_llm', target: 'node_email', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-13',
    name: '🧹 데이터 클렌징 파이프라인',
    description: '정제되지 않은 데이터를 가져와 Python 스크립트로 클렌징한 뒤, DB에 저장합니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_db_in', type: 'databaseNode', position: { x: 300, y: 150 }, data: { label: '원본 데이터 추출', connectionString: 'sqlite:///test.db', query: 'SELECT name FROM users;' } },
        { id: 'node_py', type: 'pythonNode', position: { x: 600, y: 150 }, data: { label: '클렌징 스크립트', code: 'output_data = str(input_data).replace("null", "Unknown")' } },
        { id: 'node_db_out', type: 'databaseNode', position: { x: 900, y: 150 }, data: { label: '정제 데이터 저장', connectionString: 'sqlite:///test.db', query: '-- UPDATE test ...' } }
      ],
      edges: [
        { id: 'e_s-d', source: 'node_start', target: 'node_db_in', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_d-p', source: 'node_db_in', target: 'node_py', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_p-do', source: 'node_py', target: 'node_db_out', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-14',
    name: '⏲️ 지연 리마인더',
    description: '지정된 시간 동안 대기한 후 카카오톡으로 리마인더 알림을 보냅니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: '리마인더 입력', inputLabel: '무엇을 리마인드할까요?' } },
        { id: 'node_delay', type: 'delayNode', position: { x: 600, y: 150 }, data: { label: '30초 대기', seconds: 30 } },
        { id: 'node_kakao', type: 'kakaoNode', position: { x: 900, y: 150 }, data: { label: '카카오 리마인드', receiver: '나에게' } }
      ],
      edges: [
        { id: 'e_s-i', source: 'node_start', target: 'node_in', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_i-d', source: 'node_in', target: 'node_delay', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_d-k', source: 'node_delay', target: 'node_kakao', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-15',
    name: '🧠 복합 이벤트 프로세서',
    description: '뉴스 크롤링 -> 정보 추출 -> 요약 -> 담당자 승인 -> 이메일 발송 파이프라인입니다.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_crawl', type: 'webCrawlerNode', position: { x: 300, y: 150 }, data: { label: '뉴스 크롤링', url: 'https://news.ycombinator.com' } },
        { id: 'node_parse', type: 'jsonParserNode', position: { x: 550, y: 150 }, data: { label: '본문 추출', mode: 'extract', extractKey: 'body' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 800, y: 150 }, data: { label: '요약기', model: 'gemini-3.5-flash', systemPrompt: '크롤링된 뉴스를 3개의 항목으로 요약하세요.' } },
        { id: 'node_approval', type: 'humanApprovalNode', position: { x: 1100, y: 150 }, data: { label: '승인 절차', message: '요약 내용을 이메일로 전송할까요?' } },
        { id: 'node_email', type: 'emailNode', position: { x: 1400, y: 150 }, data: { label: '이메일 발송', toEmail: 'team@example.com' } }
      ],
      edges: [
        { id: 'e_s-c', source: 'node_start', target: 'node_crawl', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_c-p', source: 'node_crawl', target: 'node_parse', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_p-l', source: 'node_parse', target: 'node_llm', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_l-a', source: 'node_llm', target: 'node_approval', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_a-e', source: 'node_approval', target: 'node_email', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  },
  {
    id: 'builtin-16',
    name: '🤖 디스코드 AI 챗봇',
    description: '디스코드 채널의 메시지를 받아 LLM이 답변하는 상호작용형 봇 템플릿입니다.',
    usage: '1. 디스코드 개발자 포털에서 봇 토큰을 발급받으세요. (Message Content Intent 활성화 필수)\n2. [Deploy] 모달에서 "디스코드 봇" 배포 모드를 선택하고 토큰을 입력하세요.\n3. 디스코드에서 봇을 역할이 아닌 유저로 직접 멘션하여 대화를 시작하세요.',
    url: 'https://discord.com/developers/applications',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '시작' } },
        { id: 'node_dyn', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: '사용자 채팅', inputLabel: '디스코드 메시지 입력' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 650, y: 150 }, data: { label: 'AI 답변 생성', model: 'gemini-3.5-flash', systemPrompt: '당신은 디스코드 서버의 유쾌한 AI 매니저입니다. 반말로 재치있게 답변해주세요.' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1000, y: 150 }, data: { label: '디스코드 전송 (출력)' } }
      ],
      edges: [
        { id: 'e_s-d', source: 'node_start', target: 'node_dyn', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_d-l', source: 'node_dyn', target: 'node_llm', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_l-o', source: 'node_llm', target: 'node_out', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  }
];

export default function TemplateModal({ isOpen, onClose, onSave, onLoad, currentFlowData }) {
  const [savedTemplates, setSavedTemplates] = useState([]);
  const [newTemplateName, setNewTemplateName] = useState('');
  const [infoTemplate, setInfoTemplate] = useState(null);

  useEffect(() => {
    if (isOpen) {
      const stored = localStorage.getItem('user_templates');
      if (stored) {
        try {
          setSavedTemplates(JSON.parse(stored));
        } catch (e) {
          console.error('Failed to parse templates', e);
        }
      }
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = () => {
    if (!newTemplateName.trim()) return alert('Please enter a template name.');
    
    const newTemplate = {
      id: `usr-${Date.now()}`,
      name: newTemplateName.trim(),
      description: 'User saved template',
      data: currentFlowData()
    };
    
    const updated = [...savedTemplates, newTemplate];
    localStorage.setItem('user_templates', JSON.stringify(updated));
    setSavedTemplates(updated);
    setNewTemplateName('');
  };

  const handleDelete = (id) => {
    if (!window.confirm('Delete this template?')) return;
    const updated = savedTemplates.filter(t => t.id !== id);
    localStorage.setItem('user_templates', JSON.stringify(updated));
    setSavedTemplates(updated);
  };

  const loadTemplate = (template) => {
    if (window.confirm(`Load template "${template.name}"? This will overwrite your current canvas.`)) {
      onLoad(template.data);
      onClose();
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2><Folder size={20} /> Templates Manager</h2>
          <button className="btn-icon" onClick={onClose}><X size={20}/></button>
        </div>

        <div className="modal-body">
          <div className="template-section">
            <h3>Save Current Flow</h3>
            <div className="save-flow-row">
              <input 
                type="text" 
                placeholder="Enter template name..." 
                value={newTemplateName}
                onChange={e => setNewTemplateName(e.target.value)}
              />
              <button className="btn-primary" onClick={handleSave}>
                <Save size={16} /> Save
              </button>
            </div>
          </div>

          <div className="template-section">
            <h3>Built-in Templates</h3>
            <div className="template-grid">
              {BUILT_IN_TEMPLATES.map(t => (
                <div key={t.id} className="template-card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <h4>{t.name}</h4>
                    <button className="btn-icon" onClick={() => setInfoTemplate(t)} title="사용 가이드"><Info size={16}/></button>
                  </div>
                  <p>{t.description}</p>
                  <button className="btn-load" onClick={() => loadTemplate(t)}>
                    <Play size={16} /> Load
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="template-section">
            <h3>My Saved Templates</h3>
            {savedTemplates.length === 0 ? (
              <p className="empty-text">No saved templates yet.</p>
            ) : (
              <div className="template-grid">
                {savedTemplates.map(t => (
                  <div key={t.id} className="template-card user-template">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <h4>{t.name}</h4>
                      <button className="btn-icon delete" onClick={() => handleDelete(t.id)}><X size={16}/></button>
                    </div>
                    <p>{t.description}</p>
                    <button className="btn-load" onClick={() => loadTemplate(t)}>
                      <Play size={16} /> Load
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* Usage Info Popup */}
      {infoTemplate && (
        <div className="info-popup-overlay" onClick={() => setInfoTemplate(null)}>
          <div className="info-popup-content" onClick={e => e.stopPropagation()}>
            <div className="info-popup-header">
              <h3>{infoTemplate.name} 사용법</h3>
              <button className="btn-icon" onClick={() => setInfoTemplate(null)}><X size={20}/></button>
            </div>
            <div className="info-popup-body">
              <p style={{ whiteSpace: 'pre-line', lineHeight: '1.5', margin: '0 0 1rem 0' }}>
                {infoTemplate.usage || '1. 템플릿을 [Load] 버튼으로 불러옵니다.\n2. 캔버스에서 각 노드의 설정(파일 경로, API 키 등)을 본인의 환경에 맞게 수정합니다.\n3. [Deploy] 버튼을 눌러 파이프라인을 실행합니다.'}
              </p>
              {infoTemplate.url && (
                <div className="info-popup-url">
                  <strong>관련 링크: </strong>
                  <a href={infoTemplate.url} target="_blank" rel="noopener noreferrer">{infoTemplate.url}</a>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
