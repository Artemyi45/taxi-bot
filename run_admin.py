#!/usr/bin/env python3
import os
import subprocess
import sys

# Установим streamlit если нет
try:
    import streamlit
except ImportError:
    print("Устанавливаем streamlit...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit==1.31.0", "pandas==2.1.4", "psycopg2-binary==2.9.9"])

# Запускаем админку
os.system(f"python -m streamlit run admin_panel.py --server.port={os.environ.get('PORT', '8501')}")