# Backend
cd backend
python -m venv venv 
venv\Scripts\activate
pip install -r requirements.txt
python main.py          # → http://localhost:8000/docs

# Frontend (separate terminal)
cd frontend
npm install
npm run dev             # → http://localhost:5173