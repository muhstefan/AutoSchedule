import os
from time import sleep
import sys
from datetime import datetime
from private import KITCHEN,BATHROOM,STORAGE

now = datetime.now()  # Получаем текущую дату
today = now.date().strftime("%Y-%m-%d")


def check_project_world(test=None):
    exe_name = os.path.basename(sys.argv[0])
    if exe_name == "AutoSchedule-Кухни.exe":
        return KITCHEN
    elif exe_name == "AutoSchedule-Ванные.exe":
        return BATHROOM
    elif exe_name == "AutoSchedule-Хранение.exe":
        return STORAGE
    elif exe_name == "AutoSchedule.py":
        return test
    else:
        print(f"НЕ УКАЗАН МИР (Название должно вида AutoSchedule-Кухни.exe)")
        sleep(20)
        return None

