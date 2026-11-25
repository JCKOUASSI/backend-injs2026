@echo off
cd /d "%~dp0"
if not exist ".venv" (
    echo [SYGET-INJS] Creation de l'environnement virtuel Python...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [SYGET-INJS] Installation des dependances...
pip install -r requirements.txt -q
set DJANGO_USE_SQLITE=1
python manage.py migrate --noinput
echo =================================================================
echo  SYGET-INJS demarre sur : http://127.0.0.1:8000/
echo  Identifiants Administrateur : admin / admin
echo =================================================================
python manage.py runserver 0.0.0.0:8000
