@echo off
echo Starting Celery Worker for Document Assistant...
echo.
echo Make sure Redis is running first!
echo.

cd /d %~dp0
call venv\Scripts\activate

celery -A celery_app.celery_config:celery_app worker ^
    --loglevel=INFO ^
    --queues=documents ^
    --concurrency=2 ^
    --pool=threads ^
    --logfile=logs\celery_worker.log ^
    --hostname=worker@%%h

pause