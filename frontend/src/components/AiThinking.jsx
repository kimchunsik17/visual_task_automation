// 생성 중 표시의 **정본**.
//
// 홈 화면은 점 세 개짜리 typing-indicator 를, 에디터는 반짝임+문구+점을 쓰고 있었다. 같은 제품에서
// 같은 일(AI 가 만드는 중)을 서로 다르게 보여주면 통일감이 떨어진다. 표현을 한 곳에 두면 다시
// 갈라지지 않는다 — 새 화면에서 생성 중을 보여줄 때도 이 컴포넌트를 쓴다.
import { Sparkles } from 'lucide-react';
import './AiThinking.css';

export default function AiThinking({ label = '생성하고 있어요', size = 'sm' }) {
  const large = size === 'lg';
  return (
    <div className={`ai-thinking${large ? ' is-lg' : ''}`} role="status" aria-live="polite">
      <span className="ai-thinking-mark"><Sparkles size={large ? 17 : 15} /></span>
      <span className="ai-thinking-body">
        {/* 문구가 바뀌어도 자리가 흔들리지 않게 점은 문구 뒤에 붙인다. */}
        <strong>{label}</strong>
        <span className="ai-thinking-dots" aria-hidden="true"><i /><i /><i /></span>
      </span>
    </div>
  );
}
