@echo off
chcp 65001 > nul
pyinstaller --onefile --hidden-import=dateutil --hidden-import=gspread .\AutoSchedule.py
cd dist
copy AutoSchedule.exe AutoSchedule-Кухни.exe
copy AutoSchedule.exe AutoSchedule-Ванные.exe
copy AutoSchedule.exe AutoSchedule-Хранение.exe
del AutoSchedule.exe