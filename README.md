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

### 1. Backend Setup

1. Open a terminal and navigate to the backend directory:
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
   The backend will start at `http://localhost:8000`.

### 2. Frontend Setup

1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
   The frontend will start at `http://localhost:5173`.

## Pilot Version Verification Points

1. **UI Operation**: Open the frontend URL. You should see a "Start Trigger" node and a "Generate Summary Task" node. You can click and drag from the handle on the right of the Start node to the handle on the left of the Task node to connect them.
2. **API Communication**: Click the "Run Flow" button in the top right. Check the browser's Network tab (F12 Developer Tools). A `POST /api/execute` request should be sent with the node and edge JSON data.
3. **Graph Execution**: The backend's LangGraph parses the graph data and sends it to the Gemini API. The response from Gemini summarizing the workflow will be returned to the client and displayed in the "Execution Result" panel on the right side of the screen.
