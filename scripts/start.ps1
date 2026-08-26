Write-Host "Lancement de l'IA Personnelle ARENA Backend..." -ForegroundColor Cyan
Set-Location C:\Users\Saer\personal_ai
.\.venv\Scripts\Activate.ps1
uvicorn apps.backend.main:app --host 127.0.0.1 --port 8000 --reload