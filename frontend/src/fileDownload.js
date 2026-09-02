// 실행 결과의 uploads/<파일명> 경로를 실제 파일로 내려받는다.
//
// 예전에는 <a href="/uploads/..."> 로 정적 마운트를 직접 열었지만, 2026-08-31 보안 리뷰로
// /uploads/{stored_name} 이 소유자 인증 라우트가 되면서 일반 내비게이션(Authorization
// 헤더가 실리지 않는다)은 {"detail":"Not authenticated"} JSON 페이지만 보게 됐다.
// fetch 에 토큰을 실어 blob 으로 받고, 오브젝트 URL 로 저장을 트리거한다.
export async function downloadUploadFile(filePath, token) {
  const cleanPath = String(filePath).replace(/\\/g, '/');
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
