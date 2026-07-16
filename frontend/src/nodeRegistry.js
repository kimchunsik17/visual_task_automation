export const NodeRegistry = {
  slackNode: {
    type: 'slackNode',
    label: 'Slack 메세지',
    category: 'integration',
    color: '#0ea5e9', // e.g., skyblue for Slack
    headerColor: 'linear-gradient(135deg, #0ea5e9, #0284c7)',
    fields: [
      { name: 'channel', type: 'text', label: '채널명 (예: #general)', placeholder: '#general' },
      { name: 'message', type: 'textarea', label: '메시지', placeholder: '보낼 메시지를 입력하세요' }
    ]
  },
  paymentLinkNode: {
    type: 'paymentLinkNode',
    label: '결제 링크 생성',
    category: 'integration',
    color: '#03c75a', // default green for Naver, or mixed
    headerColor: 'linear-gradient(135deg, #03c75a, #3182f6)',
    fields: [
      { name: 'provider', type: 'text', label: '결제사 (toss 또는 naver)', placeholder: 'toss' },
      { name: 'orderData', type: 'textarea', label: '주문 정보 데이터 (JSON, 텍스트 가능)', placeholder: '{{last_result}}' }
    ]
  }
};
