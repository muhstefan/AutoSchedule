import copy
import re

import gspread
from data import TimeHelper ,SPP, num_days, month_check
from google.oauth2.service_account import Credentials
from private import credentials, SCOPES



class GoogleSheetCore:
    world_names = ["кухни", "хранение", "столярные изделия", "стройка", "ванные", "конец"]
    def __init__(self,main_data):

        credentials_new = Credentials.from_service_account_info(credentials,scopes=SCOPES)
        gc = gspread.authorize(credentials_new)

        self.worksheet = gc.open("График СППО 2025").worksheet(f"{month_check} {TimeHelper.get_year()}")
        self.all_data = self.worksheet.get_all_values()
        self.world_name_place = None
        self.ldap_place = None
        self.spp_name_place = None
        self.need_time_column = None
        self.month_start = None
        self.month_end = None
        self.current_row = None
        self.type_shift = None
        self.main_data = main_data
        self.ldap_sets = main_data.get_ldap_set()



    def find_indexes(self,data):
        for index, thing  in enumerate(data):
            if thing:
                if "ldap" in thing.lower():
                    self.ldap_place = index
                    continue
                if month_check.lower() in thing.lower():
                    self.month_start = index
                    self.month_end = self.month_start + num_days
                    continue
                if "фамилия" in thing.lower() or "фио" in thing.lower():
                    self.spp_name_place = index
                    continue
                if "вых" in thing.lower():
                    self.type_shift = index
                    continue


    # def check_world(self):
    #     for name in self.world_names:
    #         if name.lower() in self.current_row[self.world_name_place].lower():
    #             self.current_world = name
    #             return 1

    @staticmethod
    def is_valid_time_pair(time_str):
        pattern = r"^([01]?[0-9]|2[0-3]):00\s*\n?\s*([01]?[0-9]|2[0-3]):00$"
        return bool(re.fullmatch(pattern, time_str))


    def check_spp(self):
        ldap = self.current_row[self.ldap_place]
        check = ldap.isdigit()
        check_2 = ldap.isalpha()
        time_table = SPP.create_month()
        status = self.current_row[self.type_shift]
        if check and not check_2 and int(ldap) in self.ldap_sets:
            for i,time in enumerate(self.current_row[self.month_start:self.month_end],start=1):
                key = f"{i:02d}"  # Преобразуем i в строку с ведущим нулём
                if GoogleSheetCore.is_valid_time_pair(time):
                    pattern = r"(?:[01]?[0-9]|2[0-3]):00" # ищем только нужное
                    times = re.findall(pattern, time)
                    time_table[key].extend(times)
                    continue
                time_table[key].append(time)

            self.main_data.get_spp(int(ldap)).schedule = time_table
            self.main_data.get_spp(int(ldap)).status = status
            self.main_data.get_spp(int(ldap)).post_table = copy.deepcopy(time_table)

    # def find_date(self,index):
    #     need_row = index+2
    #     for i,world in enumerate(self.all_data[need_row]):
    #         if str(yesterday_day) in world:
    #             self.need_time_column = i


    def read_table(self):
        for i, row in enumerate(self.all_data):
            if "ldap" in row or "LDAP" in row:
                self.find_indexes(row)
                break
        for row in self.all_data:
            self.current_row = row
            self.check_spp()




