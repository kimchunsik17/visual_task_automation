// 실행 결과의 uploads/<파일명> 경로를 실제 파일로 내려받는다.
//
// 예전에는 <a href="/uploads/..."> 로 정적 마운트를 직접 열었지만, 2026-08-31 보안 리뷰로
// /uploads/{stored_name} 이 소유자 인증 라우트가 되면서 일반 내비게이션(Authorization
// 헤더가 실리지 않는다)은 {"detail":"Not authenticated"} JSON 페이지만 보게 됐다.
// fetch 에 토큰을 실어 blob 으로 받고, 오브젝트 URL 로 저장을 트리거한다.
// 결과 문자열에서 생성 파일 경로 하나를 찾는다. RegExp match 와 같은 모양([0]=원문, index)을 돌려주므로
// 앞뒤 텍스트를 잘라 쓰는 화면(앱 뷰어·앱 러너)이 그대로 쓸 수 있다.
//
// 2026-09-06 부스 점검에서 두 가지가 한꺼번에 드러났다.
//  - 파일명에 공백이 있다(한글 포맷 이름: "여행 일정표_dc9faf.docx"). 예전 정규식 /uploads\/[^\s]+/ 는
//    "uploads/여행" 에서 끊겨 404("파일을 찾을 수 없거나 내려받을 권한이 없습니다").
//  - 이메일 노드는 본문 뒤에 "\n\n[📎 첨부 1개: …]" 안내를 붙인다. 문자열 전체를 경로로 쓰면 URL 파서가
//    개행을 지워 "…docx[📎…" 를 요청한다.
// 그래서 확장자로 끝을 잡고(공백 허용), 확장자를 모르는 경우에만 줄 끝·'['·따옴표 앞까지로 물러난다.
const KNOWN_EXT = 'docx|hwpx|hwp|pdf|png|jpe?g|gif|webp|svg|xlsx|xls|csv|pptx|txt|md|json|zip|mp4|mp3|wav';
const PATH_BY_EXT = new RegExp(`uploads[\\/](?:u\\d+[\\/])?[^\\r\\n\\[\\]"'<>]+?\\.(?:${KNOWN_EXT})(?![\\w.])`, 'i');
const PATH_TO_LINE_END = /uploads[\\/][^\r\n[\]"'<>]+/;

export function matchUploadPath(text) {
  if (typeof text !== 'string') return null;
  const m = text.match(PATH_BY_EXT) || text.match(PATH_TO_LINE_END);
  if (!m) return null;
  const raw = m[0].replace(/[\s.,;:)]+$/, '');          // 문장 끝 구두점·공백은 경로가 아니다
  const out = [raw];
  out.index = m.index;
  return out;
}

export function extractUploadPath(text) {
  const m = matchUploadPath(text);
  return m ? m[0].replace(/\\/g, '/') : null;
}

export async function downloadUploadFile(filePath, token) {
  // 호출자가 결과 문자열 전체를 넘겨도 경로만 골라 쓴다 — 첨부 안내·설명 문장이 붙어 와도 안전하다.
  const cleanPath = (extractUploadPath(filePath) || String(filePath)).replace(/\\/g, '/');
  const fileName = cleanPath.split('/').pop();
  const res = await fetch(`/${cleanPath}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    if (res.status === 401) throw new Error('로그인이 필요합니다.');
    // 서버는 남의 파일에 404 를 준다(존재를 알리지 않는다) — 권한 문구를 함께 쓴다.
    if (res.status === 404) throw new Error('파일을 찾을 수 없거나 내려받을 권한이 없습니다.');
    throw new Error(`다운로드에 실패했습니다 (HTTP ${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
  return fileName;
}
