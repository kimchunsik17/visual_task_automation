# Business Automation Visualization Tool Pilot

This project is a pilot prototype for a business automation visualization tool. It consists of a React (Vite) frontend with React Flow, and a Python FastAPI backend with LangGraph and Gemini integration, backed by PostgreSQL.

## Folder Structure

- `/frontend` - React + Vite application. Contains the React Flow canvas.
- `/backend` - FastAPI Python application. Contains the LangGraph workflow and DB configuration.

## Prerequisites

- **Node.js**: Required to install and run the React frontend (npm or yarn).
- **Python 3.10+**: Required to run the FastAPI backend.
- **PostgreSQL**: Optional for the pilot, but the connection string is prepared for it.
- **Gemini API Key**: Required for the LangGraph agent to generate responses.

## Setup Instructions

### 1. Frontend Build

1. Open a terminal and navigate to the frontend directory:
   ```bash
   필수 cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Build the frontend static files:
   ```bash
   npm run build
   ```
   *(Note: For frontend-only development, you can use `npm run dev` instead).*

### 2. Backend Setup (Single Server)

1. Open a new terminal and navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up Environment Variables:
   - Copy `.env.example` to `.env` in the `backend` directory.
   - Insert your `GEMINI_API_KEY`.
   - Update `DATABASE_URL` with your PostgreSQL credentials (e.g., `postgresql://postgres:password@localhost/dbname`). 
5. Run the FastAPI server:
   ```bash
   uvicorn main:app --reload
   ```
   The application will start at `http://localhost:8000`. FastAPI will automatically serve both the backend API and the compiled React frontend.

## Pilot Version Verification Points

1. **UI Operation**: Open the frontend URL. You should see a "Start Trigger" node and a "Generate Summary Task" node. You can click and drag from the handle on the right of the Start node to the handle on the left of the Task node to connect them.
2. **API Communication**: Click the "Run Flow" button in the top right. Check the browser's Network tab (F12 Developer Tools). A `POST /api/execute` request should be sent with the node and edge JSON data.
3. **Graph Execution**: The backend's LangGraph parses the graph data and sends it to the Gemini API. The response from Gemini summarizing the workflow will be returned to the client and displayed in the "Execution Result" panel on the right side of the screen.

## CI

`.github/workflows/ci.yml` 이 `main`·`dev`·`release` 로 가는 push/PR 마다 돈다. 비밀은 필요 없다.

| job | 하는 일 |
| --- | --- |
| backend | Python 3.10 · `pip install -r backend/requirements.txt` · `python export_node_definitions.py --check`(노드 정의 ↔ 프론트 번들 동기화) · **전체 pytest**(sqlite — `DATABASE_URL` 없이 `conftest.py` 가 강제; PostgreSQL 전용 테스트는 `TEST_POSTGRES_URL` 없으면 skip) |
| frontend | Node 22 · `npm ci` · `node --test src/*.test.js` · `eslint --quiet`(오류만 — 경고는 기존 기준) · `vite build` |

로컬에서 같은 것을 돌리려면:

```bash
cd backend && venv/Scripts/python -m pytest -p no:cacheprovider -q          # Windows; 리눅스는 venv/bin/python
cd backend && venv/Scripts/python export_node_definitions.py --check
cd frontend && node --test src/*.test.js && npx eslint . --quiet && npm run build
```

전체 suite 를 도는 이유: 스택 PR 을 "관련 파일 묶음" 으로만 회귀했을 때 전체에서만 드러나는 실패가 두 번 있었다(2026-09-11). 3,100건이 2~3분이다.
