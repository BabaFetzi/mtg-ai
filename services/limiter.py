"""
services/limiter.py – Zentraler Rate-Limiter (slowapi)

Nutzt Redis als geteilten Storage-Backend, damit Limits über mehrere
Worker/Prozesse hinweg konsistent durchgesetzt werden. Ist REDIS_URL nicht
gesetzt, fällt slowapi automatisch auf einen In-Memory-Storage zurück
(nur für lokale Entwicklung geeignet, nicht für Multi-Worker-Deployments).
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, storage_uri=os.getenv("REDIS_URL"))
