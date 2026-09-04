// features.js — /api/features 배포 플래그의 공용 조회 지점.
//
// 시연 노드 비가시화(hidden_nodes)처럼 여러 화면이 같은 플래그를 봐야 할 때, 화면마다
// 따로 요청하지 않도록 한 번만 불러 캐시한다. 실패하면 빈 플래그(= 현행 동작)로 둔다.
import axios from 'axios';

let featuresPromise = null;
let featuresData = null;
let hiddenNodeTypes = new Set();
let demoUi = false;

export const loadFeatures = () => {
  if (!featuresPromise) {
    featuresPromise = axios.get('/api/features')
      .then((res) => {
        featuresData = res.data || {};
        hiddenNodeTypes = new Set(featuresData.hidden_nodes || []);
        demoUi = Boolean(featuresData.demo_ui);
        return featuresData;
      })
      .catch(() => ({}));
  }
  return featuresPromise;
};

// 마지막 응답 payload 동기 조회 — 아직 로드 전이면 null.
// 재마운트되는 컴포넌트(예: MainSidebar)가 첫 렌더부터 올바른 상태로 그릴 때 쓴다.
// 첫 렌더를 기본값으로 그렸다가 응답 후 바꾸면 플래그로 숨긴 메뉴가 한 프레임
// 나타났다 사라지며 레이아웃이 출렁인다(잔상 버그).
export const getFeaturesData = () => featuresData;

// 동기 조회 — loadFeatures() 가 끝나기 전에는 빈 Set(아무것도 숨기지 않음)이다.
export const getHiddenNodeTypes = () => hiddenNodeTypes;

// 시연 UI 트림(DEMO_UI) — API 센터·쪽지·통계처럼 부스에서 불필요한 표면을 숨길지.
export const isDemoUi = () => demoUi;
