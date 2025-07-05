import sys
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date
import pytz
import calendar

class TimeHelper:
    """Класс позволяющий работать со временем"""
    def __init__(self, time):
        self._time = parse_date(time)

    @staticmethod
    def get_all_days(month_cur, start_day=1, end_day=None):
        now_ = datetime.now()
        year_cur = now_.year
        num_days_ = calendar.monthrange(year_cur, month_cur)[1]

        # Если end_day не указан, ставим последний день месяца
        if end_day is None or end_day > num_days_:
            end_day = num_days_

        # Проверяем корректность интервала
        if start_day < 1:
            start_day = 1
        if end_day < start_day:
            return []  # пустой список, если интервал некорректен

        start_date = datetime(year_cur, month_cur, start_day)
        days = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d")
                for i in range(end_day - start_day + 1)]
        return days


    @staticmethod
    def day_taker(time):
        return time.split('-')[2][:2]

    @staticmethod
    def create_key_data(key):
        return  f"{first_part}-{key}"


    @staticmethod
    def hour_taker(time):
        dt = datetime.strptime(time, "%Y-%m-%dT%H:%M:%S.%fZ")
        return dt.strftime("%H:%M:%S")


    @staticmethod
    def delta_time_hours(hour,delta_hour):
        delta = timedelta(hours=delta_hour)
        hour_dt = datetime.strptime(hour, "%H:%M") + delta
        need_date = hour_dt.strftime("%H:%M")
        return need_date

    @staticmethod
    def create_need_time(day,hour, start=False):
        delta = timedelta(hours=3,seconds=1)
        if start:
            delta = timedelta(hours=3)
        hour_dt = datetime.strptime(hour, "%H:%M") - delta
        hour_dt_full = hour_dt.strftime("%H:%M:%S")
        need_date = f"{day}T{hour_dt_full}.000Z"
        return need_date

    @staticmethod
    def minus_day(time):
        input_datetime = datetime.strptime(time, "%Y-%m-%dT%H:%M:%S.%fZ")
        previous_day_datetime = input_datetime - timedelta(days=1)
        output_str = previous_day_datetime.strftime("%Y-%m-%d")
        return output_str

    @staticmethod
    def get_russian_month():
        try:
            current_month = int(input("На какой месяц делаем расписание? \nцифра месяца 1-12\n"))
            if 1 <= current_month <= 12:
                month_name_ru = russian_months[current_month - 1]
                input(f"Вы выбрали месяц {month_name_ru} \nНажмите ENTER если ГОТОВЫ ПРОДОЛЖИТЬ\n")
                return month_name_ru #Возвращается строковое название месяца
        except:
            print("Ошибка: введено не число. Программа завершена.")
            input("Нажмите ENTER для выхода...")
            sys.exit()


    @staticmethod
    def get_year():
        return datetime.now().year

    def get_data(self):
        return self._t_moscow_converter()

    # Нет смысла приводить к МСК, т.к это разница, она одинаковая всегда
    def delta_in_minutes(self,second_time):
        time = self._t_moscow_converter()
        time2 = TimeHelper(second_time)._t_moscow_converter()
        delta = time - time2
        difference_in_minutes = delta.total_seconds() / 60
        return int(difference_in_minutes)

    # Сюда уже приходит правильное время потому, что в URL запросе есть time_zone
    def one_hour_convert(self):
        formatted_time = self._time.strftime('%H')
        return int(formatted_time)

    def datetime_to_str(self,dig):
        #strftime dt -> str
        #strptime str -> dt
        self._time = self._t_moscow_converter()

        time_format = None
        if dig == 3:
            time_format = '%H-%M-%S'
        if dig == 5:
            time_format = "%Y-%m-%d-%H-%M"

        if isinstance(self._time, datetime):
            return self._time.strftime(time_format)


    def _t_moscow_converter(self):
        # Устанавливаем временную зону UTC и преобразуем в московское время
        moscow_time = self._time.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Europe/Moscow'))
        return moscow_time

russian_months = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
]

version = 0.985
now = datetime.now()  # Получаем текущую дату
year = now.year
month_check = TimeHelper.get_russian_month()
month  = russian_months.index(month_check) + 1

num_days = calendar.monthrange(year, month)[1]  # Количество дней в месяце

# Format : 2025-06-27T15:59:59.000Z
first_part = f"{year}-{month:02d}"


class SPP:
    def __init__(self ,ldap, name, id_in):
        self.ldap = ldap
        self.name = name
        self.id_in = id_in
        self.schedule = None
        self.post_table = None
        self.status = None
        self.errors = {}

    @staticmethod
    def create_month():
        schedule = {}
        for day in range(1, num_days + 1):
            day_str = f"{day:02d}"  # форматируем число с ведущим нулём
            schedule[day_str] = []
        return schedule


class CompositeData:
    def __init__(self):
        self.SPPs = {}    # Список спп у которых в свою очередь (ldap, имя, начало дня)
        self.blackout_id = []
        self.delete_spp = None

    def get_ldap_set(self):  # Множество реализовано по принципу хэш таблицы, поэтому быстрее
            return {spp.ldap for spp in self.SPPs.values()}

    def add_spp(self,spp):
        self.SPPs[spp.ldap] = spp

    def add_blackout_id(self,bl_id):
        self.blackout_id.append(bl_id)

    def get_spp_list(self):
        return self.SPPs

    def get_spp(self,ldap):
        for spp in self.SPPs:
            if spp == ldap:
                return self.SPPs[ldap]


instruction = """Введи запрос
при выборе режима у тебя есть 6 опции:

очистка - полностью очистить за определенный месяц расписание. Пример - (очистка)

создание - полностью заполнить за месяц расписание. Пример(создание)

очистка  лдап дата1 дата 2. Пример - (очистка 6018582 24 26)
очистить определенного спп за несколько дней , для выбора 1-го дня просто пишешь 2 раза (очистка 6018582 24 24)

создание лдап дата1 дата 2. Пример -  (создание 6018582 24 26)
тоже самое только заполняем интервал на спп

очистка дата1 дата 2  . Пример - (очистка 24 26)
очистить ВСЕХ спп в интервале

создание дата1 дата 2 . Пример - (создание 24 26)
"""
