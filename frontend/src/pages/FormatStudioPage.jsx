// 풀페이지 포맷 스튜디오 (/formats/studio?id=…) — 포맷 탭에서 진입하는 앱 빌더식 작업 공간.
// 편집 로직은 FormatStudio(variant="page") 그대로다. 워크플로우 에디터의 노드에서 여는
// 가벼운 수정("저장하고 이 노드에 적용")은 기존 모달을 계속 쓴다.
import { useNavigate, useSearchParams } from 'react-router-dom';
import FormatStudio from '../components/FormatStudio';

export default function FormatStudioPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const formatId = params.get('id') || '';
  return (
    <FormatStudio isOpen variant="page" initialFormatId={formatId}
                  onClose={() => navigate('/formats')} />
  );
}
