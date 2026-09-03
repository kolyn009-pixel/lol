"""Тонкий слой доступа к данным Stage 3.
Новые сценарии импортируют функции automation/*, не расширяя монолит database.py.
"""
from automation import waiting_list, balance_forecast, notifications, family, messaging, referrals, student_history, schedule_tools
