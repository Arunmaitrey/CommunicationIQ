@echo off
cd /d C:\Users\vinay\Downloads\CommunicationIQ\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8010
