import React, { useState, useEffect } from 'react';
import { Save, Folder, X, Play, Info } from 'lucide-react';
import './TemplateModal.css';

const BUILT_IN_TEMPLATES = [
  {
    id: 'builtin-1',
    name: '?“ ë¬¸ì„œ ?ë™ ì±„ìš°ê¸?(?´ë ¥??',
    description: 'ë¹„ì •???ìŠ¤?¸ì—???°ì´?°ë? ì¶”ì¶œ?˜ì—¬ HWP/Excel/PPT ?œí”Œë¦¿ì„ ?ë™?¼ë¡œ ì±„ì›?ˆë‹¤.',
    usage: '1. "?œí”Œë¦?ë¶„ì„ê¸? ?¸ë“œ?ì„œ ?¬ìš©??ë¬¸ì„œ ?Œì¼(.hwp, .docx ?????…ë¡œ?œí•˜?¸ìš”.\n2. "ì§€?ì ?•ë³´" ?¸ë“œ??ì²˜ë¦¬??ë¹„ì •???ìŠ¤?¸ë? ?…ë ¥?˜ì„¸??\n3. [Deploy] ë²„íŠ¼???ŒëŸ¬ ?¤í–‰ ê²°ê³¼ë¥??•ì¸?˜ì„¸??',
    url: 'https://github.com/your-repo/docs/template-filling',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_1', type: 'templateAnalyzerNode', position: { x: 300, y: 150 }, data: { label: '?œí”Œë¦?ë¶„ì„ê¸?, template_path: 'C:\\Users\\kimchunsik\\Desktop\\?…ë¬´?ë™??ë¹„ì£¼?¼í™”\\backend\\uploads\\?…ì‚¬ ì§€?ì„œ .hwp', filename: '?…ì‚¬ ì§€?ì„œ .hwp' } },
        { id: 'node_info', type: 'valueNode', position: { x: 550, y: 150 }, data: { label: 'ì§€?ì ?•ë³´', value: '?ê¸¸?™ì? ?¤ì´ë²„ì—??3?„ê°„ ë§ˆì???ê¸°íš?ë¡œ ?¼í–ˆ?µë‹ˆ?? ?°ë½ì²˜ëŠ” 010-1234-5678?´ë©° ë§ˆì????€??ì§€?í•©?ˆë‹¤.' } },
        { id: 'node_2', type: 'promptNode', position: { x: 850, y: 150 }, data: { label: '?„ë¡¬?„íŠ¸', userPrompt: '?¤ìŒ JSON ?•ì‹(keys)??ë§ê²Œ ?ìŠ¤?¸ì—???•ë³´ë¥?ì¶”ì¶œ??ì¤? ë°˜ë“œ??JSON ?•ì‹?¼ë¡œë§??€?µí•´.' } },
        { id: 'node_3', type: 'llmNode', position: { x: 1200, y: 150 }, data: { label: 'LLM', model: 'gemini-3.5-flash', systemPrompt: '?¹ì‹ ?€ ?•í™•???°ì´??ì¶”ì¶œ ?´ì‹œ?¤í„´?¸ì…?ˆë‹¤.' } },
        { id: 'node_4', type: 'fileModifierNode', position: { x: 1550, y: 150 }, data: { label: '?ë™ ì±„ìš°ê¸?, template_path: 'C:\\Users\\kimchunsik\\Desktop\\?…ë¬´?ë™??ë¹„ì£¼?¼í™”\\backend\\uploads\\?…ì‚¬ ì§€?ì„œ .hwp', filename: '?…ì‚¬ ì§€?ì„œ .hwp', output_path: 'output_filled.hwp' } }
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
    name: '?Œ ?¨ìˆœ ë²ˆì—­ ?Œì´?„ë¼??,
    description: '?…ë ¥ ?ìŠ¤?¸ë? ?¤ë¥¸ ?¸ì–´ë¡?ë²ˆì—­?˜ëŠ” ê¸°ë³¸?ì¸ ?Œì´?„ë¼?¸ì…?ˆë‹¤.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_1', type: 'valueNode', position: { x: 300, y: 150 }, data: { label: '?…ë ¥ê°?, value: 'Hello, how are you?' } },
        { id: 'node_2', type: 'llmNode', position: { x: 650, y: 150 }, data: { label: 'LLM', model: 'gpt-4o-mini', systemPrompt: '?¹ì‹ ?€ ?„ë¬¸ ë²ˆì—­ê°€?…ë‹ˆ?? ì£¼ì–´ì§??ìŠ¤?¸ë? ?œêµ­?´ë¡œ ë²ˆì—­?˜ì„¸??' } },
        { id: 'node_3', type: 'outputNode', position: { x: 1000, y: 150 }, data: { label: 'ê²°ê³¼ ì¶œë ¥' } }
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
    name: '?¤– ?™ì  ì±—ë´‡ ?œí”Œë¦?,
    description: '?™ì  ?…ë ¥ ?¸ë“œ?€ LLM???¬ìš©?˜ì—¬ ë°˜ì‘??ì±—ë´‡??ë§Œë“œ???œí”Œë¦¿ì…?ˆë‹¤.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_dyn', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: '?™ì  ?…ë ¥', inputLabel: 'ë¬´ì—‡?´ë“  ë¬¼ì–´ë³´ì„¸??' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 650, y: 150 }, data: { label: 'LLM', model: 'gemini-3.5-flash', systemPrompt: '?¹ì‹ ?€ ì¹œì ˆ??AI ?´ì‹œ?¤í„´?¸ì…?ˆë‹¤. ?¬ìš©?ì˜ ì§ˆë¬¸???µí•´ì£¼ì„¸??' } },
        { id: 'node_out', type: 'kakaoNode', position: { x: 1000, y: 150 }, data: { label: 'ì¹´ì¹´???Œë¦¼??, receiver: 'ê¸°ë³¸ ?¬ìš©?? } }
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
    name: '?“° ?™ì  ?´ìŠ¤ ?”ì•½ê¸?,
    description: '?´ìŠ¤ ê¸°ì‚¬??URL???…ë ¥?˜ë©´ ?¹ì„ ?¬ë¡¤ë§í•˜ê³? 3ì¤„ë¡œ ?”ì•½?????´ë©”?¼ë¡œ ?„ì†¡?©ë‹ˆ??',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_url', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: '?´ìŠ¤ URL ?…ë ¥', inputLabel: '?”ì•½??ê¸°ì‚¬ URL???…ë ¥?˜ì„¸?? } },
        { id: 'node_crawl', type: 'webCrawlerNode', position: { x: 550, y: 150 }, data: { label: '???¬ë¡¤??, url: '' } },
        { id: 'node_prompt', type: 'promptNode', position: { x: 850, y: 150 }, data: { label: '?”ì•½ ?„ë¡¬?„íŠ¸', userPrompt: '?¤ìŒ ?ìŠ¤?¸ë? ?½ê³  ?µì‹¬ ?´ìš©??3ì¤„ë¡œ ?”ì•½?´ì¤˜.' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 1150, y: 150 }, data: { label: 'LLM', model: 'gemini-3.5-flash', systemPrompt: '?¹ì‹ ?€ ?•í™•?˜ê³  ë¹ ë¥¸ ?´ìŠ¤ ?”ì•½ ?„ë¬¸ê°€?…ë‹ˆ??' } },
        { id: 'node_email', type: 'emailNode', position: { x: 1450, y: 150 }, data: { label: '?´ë©”???„ì†¡', toEmail: 'boss@company.com' } }
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
    name: '??ì¡°ê±´ë¶€ ?ë™ ?‘ë‹µê¸?,
    description: 'ê³ ê° ë©”ì‹œì§€ë¥?ë¶„ë¥˜?©ë‹ˆ?? ë¶ˆë§Œ ?‘ìˆ˜ë©?ë§¤ë‹ˆ?€?ê²Œ ì¹´ì¹´?¤í†¡ ?Œë¦¼?? ?¼ë°˜ ë¬¸ì˜ë©?LLM???µë??©ë‹ˆ??',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 250 }, data: { label: '?œì‘' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 250 }, data: { label: 'ê³ ê° ë©”ì‹œì§€', inputLabel: 'ê³ ê° ë¬¸ì˜ ?´ìš©' } },
        { id: 'node_class', type: 'llmNode', position: { x: 600, y: 250 }, data: { label: 'ë¶„ë¥˜ê¸?LLM', model: 'gpt-4o-mini', systemPrompt: 'ê³ ê° ë¬¸ì˜ë¥?ë¶„ì„?˜ì—¬, ë¶ˆë§Œ/?˜ë¶ˆ ?”ì²­?´ë©´ "COMPLAINT", ?¨ìˆœ ë¬¸ì˜ë©?"NORMAL"?´ë¼ê³ ë§Œ ?€?µí•´??' } },
        { id: 'node_cond', type: 'conditionNode', position: { x: 900, y: 250 }, data: { label: 'ë¶ˆë§Œ ?¬ë? ?•ì¸', condition: 'Contains', value: 'COMPLAINT' } },
        { id: 'node_kakao', type: 'kakaoNode', position: { x: 1250, y: 100 }, data: { label: '?´ë‹¹???Œë¦¼ (ì¹´ì¹´?¤í†¡)', receiver: 'CS ?´ë‹¹?? } },
        { id: 'node_reply', type: 'llmNode', position: { x: 1250, y: 400 }, data: { label: '?ë™ ?µë? LLM', model: 'gemini-3.5-flash', systemPrompt: 'ê³ ê°??ì§ˆë¬¸??ì¹œì ˆ?˜ê²Œ ?µë??˜ëŠ” CS ë´‡ì…?ˆë‹¤.' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1600, y: 400 }, data: { label: 'ìµœì¢… ?µë? ì¶œë ¥' } }
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
    name: '?Œ API ?°ì´??ê°€?¸ì˜¤ê¸?,
    description: 'ê³µê°œ API?ì„œ ?°ì´?°ë? ê°€?¸ì˜¤ê³??¹ì • ?¤ì˜ ê°’ì„ ì¶”ì¶œ?©ë‹ˆ??',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_http', type: 'httpRequestNode', position: { x: 300, y: 150 }, data: { label: 'API ?¸ì¶œ', method: 'GET', url: 'https://jsonplaceholder.typicode.com/todos/1' } },
        { id: 'node_parse', type: 'jsonParserNode', position: { x: 600, y: 150 }, data: { label: 'JSON ?Œì‹±', mode: 'parse' } },
        { id: 'node_extract', type: 'jsonParserNode', position: { x: 900, y: 150 }, data: { label: 'Title ì¶”ì¶œ', mode: 'extract', extractKey: 'title' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1200, y: 150 }, data: { label: 'ê²°ê³¼ê°? } }
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
    name: '?’¬ ?¹í›… ?Œë¦¬ë¯?,
    description: '?™ì  ?…ë ¥??ë°›ì•„ ?¬ë™?´ë‚˜ ?”ìŠ¤ì½”ë“œ ê°™ì? ?¹í›…?¼ë¡œ ?„ì†¡?©ë‹ˆ??',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: '?…ë ¥ ë©”ì‹œì§€', inputLabel: '?Œë¦¼ ë³´ë‚¼ ë©”ì‹œì§€' } },
        { id: 'node_format', type: 'pythonNode', position: { x: 550, y: 150 }, data: { label: '?˜ì´ë¡œë“œ ?¬ë§·??, code: 'import json\noutput_data = json.dumps({"content": str(input_data)})' } },
        { id: 'node_http', type: 'httpRequestNode', position: { x: 800, y: 150 }, data: { label: '?¹í›… POST', method: 'POST', url: 'https://httpbin.org/post', headers: '{"Content-Type": "application/json"}' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1100, y: 150 }, data: { label: 'ê²°ê³¼ ì¶œë ¥' } }
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
    name: '?”— ?¤ì¤‘ ?ŒìŠ¤ ë³‘í•©',
    description: '??ê°œì˜ ?¤ë¥¸ ?™ì  ?…ë ¥???˜ë‚˜??ë°°ì—´ë¡?ë³‘í•©????ë¶„ì„?©ë‹ˆ??',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 200 }, data: { label: '?œì‘' } },
        { id: 'node_in1', type: 'dynamicInputNode', position: { x: 300, y: 100 }, data: { label: '?ŒìŠ¤ A', inputLabel: '?œí’ˆ A ?¤í™' } },
        { id: 'node_in2', type: 'dynamicInputNode', position: { x: 300, y: 300 }, data: { label: '?ŒìŠ¤ B', inputLabel: '?œí’ˆ B ?¤í™' } },
        { id: 'node_merge', type: 'mergeNode', position: { x: 600, y: 200 }, data: { label: '?°ì´??ë³‘í•©', mergeStrategy: 'join_newline' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 900, y: 200 }, data: { label: 'LLM ë¹„êµ ë¶„ì„', model: 'gpt-4o-mini', systemPrompt: '???œí’ˆ???¤í™??ë¹„êµ?˜ê³  ?¥ë‹¨?ì„ ë¶„ì„?´ì£¼?¸ìš”.' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1200, y: 200 }, data: { label: 'ì¶œë ¥' } }
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
    name: '?“ ?¹ì¸ ê¸°ë°˜ ?ë™ ë°œí–‰',
    description: 'ì´ˆì•ˆ???‘ì„±?˜ë©´ LLM??êµì •?˜ê³ , ?´ë‹¹?ì˜ ?¹ì¸??ê±°ì³ ìµœì¢… ë°œí–‰?©ë‹ˆ??',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: 'ì´ˆì•ˆ ?…ë ¥', inputLabel: 'ì´ˆì•ˆ ?‘ì„±' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 600, y: 150 }, data: { label: 'LLM êµì •ê¸?, model: 'gemini-3.5-flash', systemPrompt: 'ì£¼ì–´ì§?ì´ˆì•ˆ??ë§ì¶¤ë²•ì„ êµì •?˜ê³  ?„ë¬¸ê°€ì²˜ëŸ¼ ?¤ë¬¸?´ì¤˜.' } },
        { id: 'node_approval', type: 'humanApprovalNode', position: { x: 900, y: 150 }, data: { label: '?´ë‹¹???¹ì¸', message: 'êµì •??ê¸€??ë°œí–‰?˜ì‹œê² ìŠµ?ˆê¹Œ?' } },
        { id: 'node_publish', type: 'httpRequestNode', position: { x: 1200, y: 150 }, data: { label: 'ë°œí–‰ (?¹í›…)', method: 'POST', url: 'https://httpbin.org/post' } }
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
    name: '?š¨ ?œë²„ ?íƒœ ê²½ê³  ?Œë¦¼',
    description: '?œë²„ ?íƒœë¥??•ì¸?˜ê³ , 200 OKê°€ ?„ë‹ˆë©?ì¹´ì¹´???Œë¦¼?¡ì„ ?„ì†¡?©ë‹ˆ??',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 200 }, data: { label: '?œì‘' } },
        { id: 'node_http', type: 'httpRequestNode', position: { x: 300, y: 200 }, data: { label: '?œë²„ ??(Ping)', method: 'GET', url: 'https://httpbin.org/status/500' } },
        { id: 'node_cond', type: 'conditionNode', position: { x: 600, y: 200 }, data: { label: '500 ?ëŸ¬?¸ê??', condition: 'Contains', value: '500' } },
        { id: 'node_alert', type: 'kakaoNode', position: { x: 900, y: 100 }, data: { label: 'ê´€ë¦¬ì ?Œë¦¼', receiver: 'ê´€ë¦¬ì' } },
        { id: 'node_out', type: 'outputNode', position: { x: 900, y: 300 }, data: { label: '?•ìƒ ì²˜ë¦¬?? } }
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
    name: '?“Š ê³ ê° ?¼ë“œë°?ê°ì • ë¶„ì„',
    description: 'DB?ì„œ ?¼ë“œë°±ì„ ê°€?¸ì? ê°ì •??ë¶„ì„?˜ê³ , ë¶€?•ì ??ê²½ìš° ?Œë¦¼??ë³´ëƒ…?ˆë‹¤.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_db', type: 'databaseNode', position: { x: 300, y: 150 }, data: { label: '?¼ë“œë°?ê°€?¸ì˜¤ê¸?, connectionString: 'sqlite:///feedbacks.db', query: 'SELECT content FROM feedback LIMIT 1;' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 600, y: 150 }, data: { label: 'ê°ì • ë¶„ì„ LLM', model: 'gpt-4o-mini', systemPrompt: 'ê°ì •??ë¶„ì„?˜ì—¬ ë°˜ë“œ??"NEGATIVE" ?ëŠ” "POSITIVE" ?¼ê³ ë§??µë??˜ì„¸??' } },
        { id: 'node_cond', type: 'conditionNode', position: { x: 900, y: 150 }, data: { label: 'ë¶€?•ì ?¸ê??', condition: 'Contains', value: 'NEGATIVE' } },
        { id: 'node_kakao', type: 'kakaoNode', position: { x: 1200, y: 50 }, data: { label: '?´ë‹¹???Œë¦¼', receiver: 'ë§¤ë‹ˆ?€' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1200, y: 250 }, data: { label: 'ì¡°ì¹˜ ?„ìš” ?†ìŒ' } }
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
    name: '?“ˆ ?ë™?”ëœ SEO ë¦¬í¬??,
    description: 'ê²½ìŸ???¬ì´?¸ë? ?¬ë¡¤ë§í•˜???¤ì›Œ?œë? ë¶„ì„?˜ê³ , ê²°ê³¼ ë¦¬í¬?¸ë? ?´ë©”?¼ë¡œ ?„ì†¡?©ë‹ˆ??',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_crawl', type: 'webCrawlerNode', position: { x: 300, y: 150 }, data: { label: '?¬ì´???¬ë¡¤ë§?, url: 'https://example.com' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 600, y: 150 }, data: { label: 'SEO ë¶„ì„ê¸?, model: 'gpt-4o-mini', systemPrompt: '?ìŠ¤?¸ë? ë¶„ì„?˜ì—¬ ?ìœ„ 5ê°œì˜ SEO ?¤ì›Œ?œë? ì¶”ì¶œ?˜ì„¸??' } },
        { id: 'node_email', type: 'emailNode', position: { x: 900, y: 150 }, data: { label: 'ë¦¬í¬???„ì†¡', toEmail: 'marketing@example.com' } }
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
    name: '?§¹ ?°ì´???´ë Œì§??Œì´?„ë¼??,
    description: '?•ì œ?˜ì? ?Šì? ?°ì´?°ë? ê°€?¸ì? Python ?¤í¬ë¦½íŠ¸ë¡??´ë Œì§•í•œ ?? DB???€?¥í•©?ˆë‹¤.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_db_in', type: 'databaseNode', position: { x: 300, y: 150 }, data: { label: '?ë³¸ ?°ì´??ì¶”ì¶œ', connectionString: 'sqlite:///test.db', query: 'SELECT name FROM users;' } },
        { id: 'node_py', type: 'pythonNode', position: { x: 600, y: 150 }, data: { label: '?´ë Œì§??¤í¬ë¦½íŠ¸', code: 'output_data = str(input_data).replace("null", "Unknown")' } },
        { id: 'node_db_out', type: 'databaseNode', position: { x: 900, y: 150 }, data: { label: '?•ì œ ?°ì´???€??, connectionString: 'sqlite:///test.db', query: '-- UPDATE test ...' } }
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
    name: '?²ï¸ ì§€??ë¦¬ë§ˆ?¸ë”',
    description: 'ì§€?•ëœ ?œê°„ ?™ì•ˆ ?€ê¸°í•œ ??ì¹´ì¹´?¤í†¡?¼ë¡œ ë¦¬ë§ˆ?¸ë” ?Œë¦¼??ë³´ëƒ…?ˆë‹¤.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_in', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: 'ë¦¬ë§ˆ?¸ë” ?…ë ¥', inputLabel: 'ë¬´ì—‡??ë¦¬ë§ˆ?¸ë“œ? ê¹Œ??' } },
        { id: 'node_delay', type: 'delayNode', position: { x: 600, y: 150 }, data: { label: '30ì´??€ê¸?, seconds: 30 } },
        { id: 'node_kakao', type: 'kakaoNode', position: { x: 900, y: 150 }, data: { label: 'ì¹´ì¹´??ë¦¬ë§ˆ?¸ë“œ', receiver: '?˜ì—ê²? } }
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
    name: '?§  ë³µí•© ?´ë²¤???„ë¡œ?¸ì„œ',
    description: '?´ìŠ¤ ?¬ë¡¤ë§?-> ?•ë³´ ì¶”ì¶œ -> ?”ì•½ -> ?´ë‹¹???¹ì¸ -> ?´ë©”??ë°œì†¡ ?Œì´?„ë¼?¸ì…?ˆë‹¤.',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_crawl', type: 'webCrawlerNode', position: { x: 300, y: 150 }, data: { label: '?´ìŠ¤ ?¬ë¡¤ë§?, url: 'https://news.ycombinator.com' } },
        { id: 'node_parse', type: 'jsonParserNode', position: { x: 550, y: 150 }, data: { label: 'ë³¸ë¬¸ ì¶”ì¶œ', mode: 'extract', extractKey: 'body' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 800, y: 150 }, data: { label: '?”ì•½ê¸?, model: 'gemini-3.5-flash', systemPrompt: '?¬ë¡¤ë§ëœ ?´ìŠ¤ë¥?3ê°œì˜ ??ª©?¼ë¡œ ?”ì•½?˜ì„¸??' } },
        { id: 'node_approval', type: 'humanApprovalNode', position: { x: 1100, y: 150 }, data: { label: '?¹ì¸ ?ˆì°¨', message: '?”ì•½ ?´ìš©???´ë©”?¼ë¡œ ?„ì†¡? ê¹Œ??' } },
        { id: 'node_email', type: 'emailNode', position: { x: 1400, y: 150 }, data: { label: '?´ë©”??ë°œì†¡', toEmail: 'team@example.com' } }
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
    name: '?¤– ?”ìŠ¤ì½”ë“œ AI ì±—ë´‡',
    description: '?”ìŠ¤ì½”ë“œ ì±„ë„??ë©”ì‹œì§€ë¥?ë°›ì•„ LLM???µë??˜ëŠ” ?í˜¸?‘ìš©??ë´??œí”Œë¦¿ì…?ˆë‹¤.',
    usage: '1. ?”ìŠ¤ì½”ë“œ ê°œë°œ???¬í„¸?ì„œ ë´?? í°??ë°œê¸‰ë°›ìœ¼?¸ìš”. (Message Content Intent ?œì„±???„ìˆ˜)\n2. [Deploy] ëª¨ë‹¬?ì„œ "?”ìŠ¤ì½”ë“œ ë´? ë°°í¬ ëª¨ë“œë¥?? íƒ?˜ê³  ? í°???…ë ¥?˜ì„¸??\n3. ?”ìŠ¤ì½”ë“œ?ì„œ ë´‡ì„ ??• ???„ë‹Œ ? ì?ë¡?ì§ì ‘ ë©˜ì…˜?˜ì—¬ ?€?”ë? ?œì‘?˜ì„¸??',
    url: 'https://discord.com/developers/applications',
    data: {
      nodes: [
        { id: 'node_start', type: 'startNode', position: { x: 50, y: 150 }, data: { label: '?œì‘' } },
        { id: 'node_dyn', type: 'dynamicInputNode', position: { x: 300, y: 150 }, data: { label: '?¬ìš©??ì±„íŒ…', inputLabel: '?”ìŠ¤ì½”ë“œ ë©”ì‹œì§€ ?…ë ¥' } },
        { id: 'node_llm', type: 'llmNode', position: { x: 650, y: 150 }, data: { label: 'AI ?µë? ?ì„±', model: 'gemini-3.5-flash', systemPrompt: '?¹ì‹ ?€ ?”ìŠ¤ì½”ë“œ ?œë²„??? ì¾Œ??AI ë§¤ë‹ˆ?€?…ë‹ˆ?? ë°˜ë§ë¡??¬ì¹˜?ˆê²Œ ?µë??´ì£¼?¸ìš”.' } },
        { id: 'node_out', type: 'outputNode', position: { x: 1000, y: 150 }, data: { label: '?”ìŠ¤ì½”ë“œ ?„ì†¡ (ì¶œë ¥)' } }
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
                    <button className="btn-icon" onClick={() => setInfoTemplate(t)} title="?¬ìš© ê°€?´ë“œ"><Info size={16}/></button>
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
              <h3>{infoTemplate.name} ?¬ìš©ë²?/h3>
              <button className="btn-icon" onClick={() => setInfoTemplate(null)}><X size={20}/></button>
            </div>
            <div className="info-popup-body">
              <p style={{ whiteSpace: 'pre-line', lineHeight: '1.5', margin: '0 0 1rem 0' }}>
                {infoTemplate.usage || '1. ?œí”Œë¦¿ì„ [Load] ë²„íŠ¼?¼ë¡œ ë¶ˆëŸ¬?µë‹ˆ??\n2. ìº”ë²„?¤ì—??ê°??¸ë“œ???¤ì •(?Œì¼ ê²½ë¡œ, API ??????ë³¸ì¸???˜ê²½??ë§ê²Œ ?˜ì •?©ë‹ˆ??\n3. [Deploy] ë²„íŠ¼???ŒëŸ¬ ?Œì´?„ë¼?¸ì„ ?¤í–‰?©ë‹ˆ??'}
              </p>
              {infoTemplate.url && (
                <div className="info-popup-url">
                  <strong>ê´€??ë§í¬: </strong>
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
