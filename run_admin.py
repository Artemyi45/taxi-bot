#!/usr/bin/env python3
import os
import subprocess
import sys

# Установим зависимости если нет
try:
    import streamlit
    import pandas
    import psycopg2
except ImportError:
    print("Устанавливаем зависимости...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements_admin.txt"])

# Запускаем админку напрямую
if __name__ == "__main__":
    port = os.environ.get("PORT", "8501")
    os.execl(sys.executable, "python", "-m", "streamlit", "run", "admin_panel.py", 
             "--server.port", port, 
             "--server.address", "0.0.0.0",
             "--browser.gatherUsageStats", "false")