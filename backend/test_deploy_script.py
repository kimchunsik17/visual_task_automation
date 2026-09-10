"""scripts/deploy.sh 의 배포 브랜치 가드.

왜 테스트하는가: 서버는 `release` 를 추적하고 main 은 자유롭게 머지한다는 규약은 deploy.sh 의 첫 단계가
지킨다. 그 가드가 조용히 사라지거나 조건이 뒤집히면 "main 에 머지했더니 서버가 바뀌었다" 가 되는데, 그건
운영에서만 드러난다. 임시 git 저장소에 deploy.sh 만 복사해 `--dry-run` 으로 돌려 첫 단계의 판정을 본다
(dry-run 은 서버 상태를 바꾸지 않고, 가드는 dry-run 에서도 검사한다).
"""
import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEPLOY_SH = ROOT / "scripts" / "deploy.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None or shutil.which("git") is None, reason="bash·git 이 필요하다")


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


@pytest.fixture
def repo(tmp_path):
    """deploy.sh 만 든 임시 저장소. REPO_ROOT 는 스크립트 위치에서 계산되므로 scripts/ 아래에 둔다."""
    repo = tmp_path / "app"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(DEPLOY_SH, repo / "scripts" / "deploy.sh")
    _git(repo, "init", "-q")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/release")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    return repo


def _deploy(repo, env=None):
    merged = {k: v for k, v in os.environ.items() if k != "DEPLOY_BRANCH"}
    merged.update(env or {})
    return subprocess.run(
        [BASH, "scripts/deploy.sh", "--dry-run"],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace", env=merged,
    )


def test_release_branch_passes(repo):
    proc = _deploy(repo)
    assert proc.returncode == 0, proc.stderr
    assert "release ok" in proc.stdout
    assert "배포 완료" in proc.stdout


def test_other_branch_is_refused_before_anything_else(repo):
    _git(repo, "checkout", "-q", "-b", "main")
    proc = _deploy(repo)
    assert proc.returncode == 1
    assert "현재 브랜치가 main" in proc.stderr
    assert "DEPLOY_BRANCH=main" in proc.stderr          # 일부러 내보내는 길을 알려 준다
    assert "[dry-run]" not in proc.stdout               # 태그·빌드·마이그레이션 단계까지 가지 않았다


def test_detached_head_is_refused_with_checkout_hint(repo):
    _git(repo, "checkout", "-q", "--detach")
    proc = _deploy(repo)
    assert proc.returncode == 1
    assert "detached" in proc.stderr
    assert "git checkout release" in proc.stderr


def test_deploy_branch_env_overrides_default(repo):
    _git(repo, "checkout", "-q", "-b", "hotfix")
    assert _deploy(repo).returncode == 1
    proc = _deploy(repo, env={"DEPLOY_BRANCH": "hotfix"})
    assert proc.returncode == 0, proc.stderr
    assert "hotfix ok" in proc.stdout


def test_dry_run_has_a_worker_restart_step_that_skips_without_units(repo):
    """워커 유닛(run-worker@N)이 없는 서버에서도 배포는 그대로 돈다 — 단계는 있고 건너뛴다고 말한다."""
    proc = _deploy(repo)
    assert proc.returncode == 0, proc.stderr
    assert "큐 워커 재기동" in proc.stdout
    assert proc.stdout.index("큐 워커 재기동") > proc.stdout.index("DB 마이그레이션"), "스키마 뒤에 워커"
    assert proc.stdout.index("큐 워커 재기동") < proc.stdout.index("서비스 재기동"), "워커 뒤에 API"


def test_server_scripts_parse():
    for name in ("deploy.sh", "rollback.sh", "server/08-run-worker-unit.sh"):
        proc = subprocess.run([BASH, "-n", str(ROOT / "scripts" / name)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        assert proc.returncode == 0, f"{name}: {proc.stderr}"
