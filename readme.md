# Backend
cd backend
python -m venv venv 
venv\Scripts\activate
pip install -r requirements.txt
py -3.11 -m venv venv
python main.py          # → http://localhost:8000/docs
uvicorn main:app --reload
https://github.com/UB-Mannheim/tesseract/wiki  #get tesseract
https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata (ENGLISH)

# Frontend (separate terminal)
cd frontend
npm install
npm run dev             # → http://localhost:5173


cd backend
celery -A celery_app worker --loglevel=info --pool=solo


check that redis working. https://github.com/microsoftarchive/redis/releases


