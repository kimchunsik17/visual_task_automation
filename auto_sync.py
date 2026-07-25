import time
import subprocess
import os
import sys

# 프로젝트 루트 디렉토리 설정
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def run_cmd(cmd, cwd=ROOT_DIR):
    """지정된 디렉토리에서 쉘 명령어를 실행하고 결과를 반환합니다."""
    try:
        result = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip(), ""
    except subprocess.CalledProcessError as e:
        return e.stdout.strip(), e.stderr.strip()

def has_uncommitted_changes():
    """로컬에 커밋되지 않은 변경사항이 있는지 확인합니다."""
    out, err = run_cmd("git status --porcelain")
    return len(out) > 0

def check_and_update():
    """원격 저장소의 변경사항을 확인하고 Pull을 수행합니다."""
    # 원격 브랜치 정보 업데이트
    run_cmd("git fetch")
    
    # 로컬과 원격의 최신 커밋 해시 비교
    local_hash, _ = run_cmd("git rev-parse HEAD")
    remote_hash, _ = run_cmd("git rev-parse origin/main")
    
    if local_hash != remote_hash and remote_hash != "":
        print(f"\n[AutoSync] 새로운 업데이트 감지됨! ({local_hash[:7]} -> {remote_hash[:7]})")
        
        if has_uncommitted_changes():
            print("[AutoSync] ⚠️ 주의: 현재 로컬에 커밋되지 않은 변경사항이 있어 코드가 덮어씌워질 수 있습니다.")
            print("[AutoSync] 충돌을 방지하기 위해 자동 병합을 건너뜁니다. 변경사항을 커밋하거나 되돌려주세요.")
            return

        print("[AutoSync] 코드를 다운로드(Pull) 합니다...")
        
        # 파일 변경 상태 확인 (패키지 설치 판단용)
        diff_out, _ = run_cmd(f"git diff --name-only {local_hash} {remote_hash}")
        changed_files = diff_out.split('\n')
        
        pull_out, pull_err = run_cmd("git pull origin main")
        print(pull_out)
        if pull_err:
            print(f"[AutoSync Error] {pull_err}")
            
        # 프론트엔드 패키지 변경 확인
        if any('frontend/package.json' in f for f in changed_files):
            print("[AutoSync] package.json 변경 감지! npm install을 실행합니다...")
            npm_out, _ = run_cmd("npm install", cwd=os.path.join(ROOT_DIR, 'frontend'))
            print(npm_out)
            
        # 백엔드 패키지 변경 확인
        if any('backend/requirements.txt' in f for f in changed_files):
            print("[AutoSync] requirements.txt 변경 감지! pip install을 실행합니다...")
            # 가상환경 내의 pip 사용
            pip_cmd = r".\venv\Scripts\pip install -r requirements.txt"
            pip_out, _ = run_cmd(pip_cmd, cwd=os.path.join(ROOT_DIR, 'backend'))
            print(pip_out)
            
        print("[AutoSync] ✨ 업데이트 및 서버 자동 갱신 완료!\n")

if __name__ == "__main__":
    print("==================================================")
    print("🚀 로컬 CI/CD 자동 동기화(Auto-Sync) 스크립트 시작")
    print(f"모니터링 경로: {ROOT_DIR}")
    print("이 창을 켜두시면 다른 기기에서 수정한 코드가 자동으로 반영됩니다.")
    print("==================================================")
    
    while True:
        try:
            check_and_update()
        except Exception as e:
            print(f"[AutoSync] 에러 발생: {e}")
        
        # 15초마다 확인
        time.sleep(15)
