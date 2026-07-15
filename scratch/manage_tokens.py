import os
import sys

# Add backend directory to sys.path to import database
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

from database import SessionLocal
import models

def check_tokens():
    db = SessionLocal()
    try:
        users = db.query(models.User).all()
        if not users:
            print("등록된 사용자가 없습니다.")
            return

        print("--- 현재 사용자 토큰 현황 ---")
        for u in users:
            print(f"ID: {u.id} | 이름: {u.name} | 이메일: {u.email} | 현재 토큰: {u.token_balance}")
        print("-----------------------------")
    finally:
        db.close()

def set_tokens(user_id, new_balance):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user:
            user.token_balance = new_balance
            db.commit()
            print(f"✅ 사용자(ID: {user_id}, 이름: {user.name})의 토큰이 {new_balance}으로 변경되었습니다.")
        else:
            print("❌ 해당하는 사용자를 찾을 수 없습니다.")
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) == 1:
        check_tokens()
        print("\n💡 [사용법]")
        print("특정 사용자의 토큰을 0으로 바꾸어 테스트하려면 아래와 같이 실행하세요:")
        print("python manage_tokens.py <사용자ID> <변경할토큰량>")
        print("예시: python manage_tokens.py 1 0")
    elif len(sys.argv) == 3:
        try:
            user_id = int(sys.argv[1])
            new_balance = int(sys.argv[2])
            set_tokens(user_id, new_balance)
        except ValueError:
            print("❌ 올바른 ID와 토큰량을 숫자로 입력해주세요.")
