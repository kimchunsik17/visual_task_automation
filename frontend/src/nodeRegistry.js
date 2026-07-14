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
  }
};
