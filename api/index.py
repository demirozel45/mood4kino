import sys
import os

# Ana dizini Python yoluna ekle
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
