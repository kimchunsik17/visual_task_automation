import React, { useState, useEffect } from 'react';
import { Save, Folder, X, Play } from 'lucide-react';
import './TemplateModal.css';

const BUILT_IN_TEMPLATES = [
  {
    id: 'builtin-1',
    name: '📝 Document Auto Fill (Resume)',
    description: 'Extracts data from unstructured text and auto-fills an HWP/Excel/PPT template.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_1', type: 'templateAnalyzerNode', position: { x: 300, y: 150 }, data: { label: 'Template Analyzer', template_path: 'C:\\Users\\kimchunsik\\Desktop\\업무자동화 비주얼화\\backend\\uploads\\입사 지원서 .hwp', filename: '입사 지원서 .hwp' } },
        { id: 'node_info', type: 'valueNode', position: { x: 550, y: 150 }, data: { label: 'Applicant Info', value: '홍길동은 네이버에서 3년간 마케팅 기획자로 일했습니다. 연락처는 010-1234-5678이며 마케팅 팀에 지원합니다.' } },
        { id: 'node_2', type: 'promptNode', position: { x: 850, y: 150 }, data: { label: 'Prompt', userPrompt: '다음 JSON 형식(keys)에 맞게 텍스트에서 정보를 추출해 줘. 반드시 JSON 형식으로만 대답해.' } },
        { id: 'node_3', type: 'llmNode', position: { x: 1200, y: 150 }, data: { label: 'LLM', model: 'gemini-3.5-flash', systemPrompt: 'You are a precise data extraction assistant.' } },
        { id: 'node_4', type: 'fileModifierNode', position: { x: 1550, y: 150 }, data: { label: 'Auto Fill', template_path: 'C:\\Users\\kimchunsik\\Desktop\\업무자동화 비주얼화\\backend\\uploads\\입사 지원서 .hwp', filename: '입사 지원서 .hwp', output_path: 'output_filled.hwp' } }
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
    name: '🌐 Simple Translation Flow',
    description: 'Basic flow to translate input text into another language.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_1', type: 'valueNode', position: { x: 300, y: 150 }, data: { label: 'Value', value: 'Hello, how are you?' } },
        { id: 'node_2', type: 'llmNode', position: { x: 650, y: 150 }, data: { label: 'LLM', model: 'gpt-4o-mini', systemPrompt: 'You are a professional translator. Translate the given text to Korean.' } },
        { id: 'node_3', type: 'outputNode', position: { x: 1000, y: 150 }, data: { label: 'Output' } }
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
    name: '🤖 Dynamic Chatbot Template',
    description: 'A template using Dynamic Input and LLM to create an interactive Chatbot.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
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
    name: '📰 Dynamic News Summarizer',
    description: 'Enter a URL to crawl the news article, summarize it into 3 bullet points, and send via Email.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_url', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: 'News URL Input', inputLabel: '요약할 기사 URL을 입력하세요' } },
        { id: 'node_crawl', type: 'webCrawlerNode', position: { x: 550, y: 150 }, data: { label: 'Web Crawler', url: '' } },
        { id: 'node_prompt', type: 'promptNode', position: { x: 850, y: 150 }, data: { label: 'Summarize Prompt', userPrompt: '다음 텍스트를 읽고 핵심 내용을 3줄로 요약해줘.' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 1150, y: 150 }, data: { label: 'LLM', model: 'gemini-3.5-flash', systemPrompt: '당신은 정확하고 빠른 뉴스 요약 전문가입니다.' } },
        { id: 'node_email', type: 'emailNode', position: { x: 1450, y: 150 }, data: { label: 'Send Email', toEmail: 'boss@company.com' } }
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
    name: '❓ Conditional Auto-Responder',
    description: 'Classify customer message: if complaint, notify manager via Kakao; else, reply with LLM.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 250 }, data: { label: 'Start' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 250 }, data: { label: 'Customer Message', inputLabel: '고객 문의 내용' } },
        { id: 'node_class', type: 'llmNode', position: { x: 600, y: 250 }, data: { label: 'Classifier LLM', model: 'gpt-4o-mini', systemPrompt: '고객 문의를 분석하여, 불만/환불 요청이면 "COMPLAINT", 단순 문의면 "NORMAL"이라고만 대답해라.' } },
        { id: 'node_cond', type: 'conditionNode', position: { x: 900, y: 250 }, data: { label: 'Check Complaint', condition: 'Contains', value: 'COMPLAINT' } },
        { id: 'node_kakao', type: 'kakaoNode', position: { x: 1250, y: 100 }, data: { label: 'Alert Manager (Kakao)', receiver: 'CS Manager' } },
        { id: 'node_reply', type: 'llmNode', position: { x: 1250, y: 400 }, data: { label: 'Auto Reply LLM', model: 'gemini-3.5-flash', systemPrompt: '고객의 질문에 친절하게 답변하는 CS 봇입니다.' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1600, y: 400 }, data: { label: 'Output Reply' } }
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
    name: '🌐 API Data Fetcher',
    description: 'Fetch data from public API and extract specific key.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_http', type: 'httpRequestNode', position: { x: 300, y: 150 }, data: { label: 'Fetch API', method: 'GET', url: 'https://jsonplaceholder.typicode.com/todos/1' } },
        { id: 'node_parse', type: 'jsonParserNode', position: { x: 600, y: 150 }, data: { label: 'Parse JSON', mode: 'parse' } },
        { id: 'node_extract', type: 'jsonParserNode', position: { x: 900, y: 150 }, data: { label: 'Extract Title', mode: 'extract', extractKey: 'title' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1200, y: 150 }, data: { label: 'Result' } }
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
    name: '💬 Webhook Notifier',
    description: 'Take dynamic input and send it to a webhook (e.g., Slack/Discord).',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: 'Input Message', inputLabel: '알림 보낼 메시지' } },
        { id: 'node_format', type: 'pythonNode', position: { x: 550, y: 150 }, data: { label: 'Format Payload', code: 'import json\noutput_data = json.dumps({"content": str(input_data)})' } },
        { id: 'node_http', type: 'httpRequestNode', position: { x: 800, y: 150 }, data: { label: 'POST Webhook', method: 'POST', url: 'https://httpbin.org/post', headers: '{"Content-Type": "application/json"}' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1100, y: 150 }, data: { label: 'Output' } }
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
    name: '🔗 Multi-Source Merge',
    description: 'Merge two different dynamic inputs into one array and analyze them.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 200 }, data: { label: 'Start' } },
        { id: 'node_in1', type: 'dynamicInputNode', position: { x: 300, y: 100 }, data: { label: 'Source A', inputLabel: '제품 A 스펙' } },
        { id: 'node_in2', type: 'dynamicInputNode', position: { x: 300, y: 300 }, data: { label: 'Source B', inputLabel: '제품 B 스펙' } },
        { id: 'node_merge', type: 'mergeNode', position: { x: 600, y: 200 }, data: { label: 'Merge Data', mergeStrategy: 'join_newline' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 900, y: 200 }, data: { label: 'LLM Comparison', model: 'gpt-4o-mini', systemPrompt: '두 제품의 스펙을 비교하고 장단점을 분석해주세요.' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1200, y: 200 }, data: { label: 'Output' } }
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
    name: '📝 Approval-Gated Publishing',
    description: 'Write a draft, have LLM review it, wait for human approval, then publish.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: 'Draft Input', inputLabel: '초안 작성' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 600, y: 150 }, data: { label: 'Proofreader', model: 'gemini-3.5-flash', systemPrompt: '주어진 초안의 맞춤법을 교정하고 전문가처럼 윤문해줘.' } },
        { id: 'node_approval', type: 'humanApprovalNode', position: { x: 900, y: 150 }, data: { label: 'Manager Approval', message: '교정된 글을 발행하시겠습니까?' } },
        { id: 'node_publish', type: 'httpRequestNode', position: { x: 1200, y: 150 }, data: { label: 'Publish (Mock)', method: 'POST', url: 'https://httpbin.org/post' } }
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
    name: '🚨 Health Check Alert',
    description: 'Ping a server. If the status is not 200 OK, alert via Kakao.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 200 }, data: { label: 'Start' } },
        { id: 'node_http', type: 'httpRequestNode', position: { x: 300, y: 200 }, data: { label: 'Ping Server', method: 'GET', url: 'https://httpbin.org/status/500' } },
        { id: 'node_cond', type: 'conditionNode', position: { x: 600, y: 200 }, data: { label: 'Is 500 Error?', condition: 'Contains', value: '500' } },
        { id: 'node_alert', type: 'kakaoNode', position: { x: 900, y: 100 }, data: { label: 'Alert Admin', receiver: 'Admin' } },
        { id: 'node_out', type: 'outputNode', position: { x: 900, y: 300 }, data: { label: 'All Good' } }
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
    name: '📊 Feedback Sentiment Pipeline',
    description: 'Fetch feedbacks from DB, analyze sentiment, alert if negative.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_db', type: 'databaseNode', position: { x: 300, y: 150 }, data: { label: 'Fetch Feedback', connectionString: 'sqlite:///feedbacks.db', query: 'SELECT content FROM feedback LIMIT 1;' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 600, y: 150 }, data: { label: 'Sentiment LLM', model: 'gpt-4o-mini', systemPrompt: 'Analyze the sentiment. Return exactly "NEGATIVE" or "POSITIVE".' } },
        { id: 'node_cond', type: 'conditionNode', position: { x: 900, y: 150 }, data: { label: 'Is Negative?', condition: 'Contains', value: 'NEGATIVE' } },
        { id: 'node_kakao', type: 'kakaoNode', position: { x: 1200, y: 50 }, data: { label: 'Alert Manager', receiver: 'Manager' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1200, y: 250 }, data: { label: 'No Action Needed' } }
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
    name: '📈 Automated SEO Report',
    description: 'Crawl competitor site, analyze keywords, send via email.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_crawl', type: 'webCrawlerNode', position: { x: 300, y: 150 }, data: { label: 'Crawl Site', url: 'https://example.com' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 600, y: 150 }, data: { label: 'SEO Analyzer', model: 'gpt-4o-mini', systemPrompt: 'Analyze this text and extract top 5 SEO keywords.' } },
        { id: 'node_email', type: 'emailNode', position: { x: 900, y: 150 }, data: { label: 'Send Report', toEmail: 'marketing@example.com' } }
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
    name: '🧹 Data Cleansing Flow',
    description: 'Fetch messy data, run Python script to clean it, mock save to DB.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_db_in', type: 'databaseNode', position: { x: 300, y: 150 }, data: { label: 'Raw Data', connectionString: 'sqlite:///test.db', query: 'SELECT name FROM users;' } },
        { id: 'node_py', type: 'pythonNode', position: { x: 600, y: 150 }, data: { label: 'Cleanse Script', code: 'output_data = str(input_data).replace("null", "Unknown")' } },
        { id: 'node_db_out', type: 'databaseNode', position: { x: 900, y: 150 }, data: { label: 'Save Data', connectionString: 'sqlite:///test.db', query: '-- UPDATE test ...' } }
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
    name: '⏲️ Delayed Reminder',
    description: 'Wait for specified seconds before sending a Kakao notification.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: 'Reminder Task', inputLabel: '무엇을 리마인드할까요?' } },
        { id: 'node_delay', type: 'delayNode', position: { x: 600, y: 150 }, data: { label: 'Wait 30s', seconds: 30 } },
        { id: 'node_kakao', type: 'kakaoNode', position: { x: 900, y: 150 }, data: { label: 'Kakao Reminder', receiver: 'Me' } }
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
    name: '🧠 Complex Event Processor',
    description: 'Crawl -> Extract -> Summarize -> Approve -> Notify Pipeline.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: 'Start' } },
        { id: 'node_crawl', type: 'webCrawlerNode', position: { x: 300, y: 150 }, data: { label: 'Crawl News', url: 'https://news.ycombinator.com' } },
        { id: 'node_parse', type: 'jsonParserNode', position: { x: 550, y: 150 }, data: { label: 'Extract Body (Mock)', mode: 'extract', extractKey: 'body' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 800, y: 150 }, data: { label: 'Summarize', model: 'gemini-3.5-flash', systemPrompt: 'Summarize the crawled news into 3 bullets.' } },
        { id: 'node_approval', type: 'humanApprovalNode', position: { x: 1100, y: 150 }, data: { label: 'Approval', message: '요약 내용을 이메일로 전송할까요?' } },
        { id: 'node_email', type: 'emailNode', position: { x: 1400, y: 150 }, data: { label: 'Send Email', toEmail: 'team@example.com' } }
      ],
      edges: [
        { id: 'e_s-c', source: 'node_start', target: 'node_crawl', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_c-p', source: 'node_crawl', target: 'node_parse', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_p-l', source: 'node_parse', target: 'node_llm', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_l-a', source: 'node_llm', target: 'node_approval', sourceHandle: 'out', targetHandle: 'in' },
        { id: 'e_a-e', source: 'node_approval', target: 'node_email', sourceHandle: 'out', targetHandle: 'in' }
      ]
    }
  }
];

export default function TemplateModal({ isOpen, onClose, onSave, onLoad, currentFlowData }) {
  const [savedTemplates, setSavedTemplates] = useState([]);
  const [newTemplateName, setNewTemplateName] = useState('');

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
                  <h4>{t.name}</h4>
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
    </div>
  );
}
