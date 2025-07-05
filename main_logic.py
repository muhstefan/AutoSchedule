import copy

from google_sheets import GoogleSheetCore
from data import *
from private import *
from world import *
import aiohttp
import asyncio
import ssl
import logging

#Текущий проектный мир (в зависимости от мира меняются правила составления расписания)
main_world = check_project_world(KITCHEN)


logging.basicConfig(
    level=logging.INFO,
    filename='app.txt',
    filemode='w',  # 'a' — дозапись, 'w' — перезапись при каждом запуске
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logging.info("Программа запущена")


class Processor:
    """Обрабатывает запросы внутри себя имеет разные модули обработки"""
    def __init__(self):  # При инициализации мы передаем json объект с которым будет работа.
        self._json = None  # Данные
        self._strategy = None  # Тип обработки
        self._main_data = CompositeData()


    def set_spp(self,spp):
        self._strategy.spp = spp

    def set_post(self,post):
        self._strategy.post = post

    def set_status(self,status):
        self._strategy.status = status

    def set_text(self,text):
        self._strategy.text = text


    def set_json(self,json):
        self._json = json

    def add_spp(self,spp):
        self._main_data.add_spp(spp)

    def add_blackout_id(self, bl_id):
        self._main_data.add_blackout_id(bl_id)

    @property
    def get_json(self):
        return self._json


    def get_data(self):
        return self._main_data

    def parse(self):
        self._strategy.parse()

    @staticmethod
    def _get_path_data(data, path):
        keys = path.split('.')
        for key in keys:
            data = data.get(f'{key}')
        return data


    class PostRequester:
        def __init__(self, processor):  # Принимает экземпляр Processor
            self.processor = processor  # Сохраняем ссылку на верхний класс
            self.spp = None
            self.text = None
            self.status = None
            self.post = None
            self.error_type = None

        # post_template = {
        #     "resourceId": None,
        #     "type": "TRAINING",  # LUNCH   \    TASK_HANDLING
        #     "capacity": 1,
        #     "startedAt": None,
        #     "finishedAt": None  # Format : 2025-06-27T15:59:59.000Z
        # }

        type_comparison = {
            "TRAINING" : "ПЕРЕКРЫТЬ",
            "LUNCH" : "ОБЕД" ,
            "TASK_HANDLING" :  "АКТИВНОСТЬ",
            "VACATION" : "ВЫХОДНОЙ/ОТПУСК"
        }




        def parse(self):
            if self.status == 200:
                # logging.info(f"Успех. Сотрудник - {self.spp.name}")  # Мы не знаем что именно успех.
                pass
            else:
                self.error_stat()


        def error_stat(self):  # Подставляем название в наш словарик и все)
            self.error_type = Processor.PostRequester.type_comparison.get(self.post["type"])
            if self.post["type"] == "TRAINING":
                if TimeHelper.hour_taker(self.post["startedAt"]) == "03:00:00":
                    self.error_type = self.error_type + " " + "УТРО"
                else:
                    self.error_type = self.error_type + " " + "ВЕЧЕР"
            key = TimeHelper.day_taker(self.post['startedAt']) # Если нет добавляем ключ, если есть то данные
            if key in self.spp.errors:
                self.spp.errors[key].append(self.error_type)
            else:
                self.spp.errors[key] = [self.error_type]


    class PassREQ:
        def __init__(self, processor):  # Принимает экземпляр Processor
            self.processor = processor     # Сохраняем ссылку на верхний класс

        def parse(self):
            pass


    class EqDelRequester:
        def __init__(self, processor):  # Принимает экземпляр Processor
            self.processor = processor     # Сохраняем ссылку на верхний класс

        def parse(self):
            self._all_spp()

        def _all_spp(self):
            delete_spp = self.processor.get_data().delete_spp  # Получаем значение delete_spp
            for resource in self.processor.get_json.get('resources', []):
                ldap = resource.get("ldap")
                # Если delete_spp задан, обрабатываем только совпадающие ldap
                if delete_spp and ldap != delete_spp:
                    continue  # пропускаем ресурс, если ldap не совпадает
                if resource.get("blackouts"):
                    for blackout in resource.get("blackouts"):
                        blackout_id = blackout.get("id")
                        self.processor.add_blackout_id(blackout_id)


    class EqRequester:
        def __init__(self, processor):  # Принимает экземпляр Processor
            self.processor = processor     # Сохраняем ссылку на верхний класс

        def parse(self):
            self._all_spp()

        def _all_spp(self):  # Делаем все тоже что и в процессорах. Как будто, получаем доступ к данным
            for resource in self.processor.get_json.get('resources', []):
                self._add_spp(resource)

        def _add_spp(self, resource ):
            spp_ldap = resource.get('ldap')
            spp_id = resource.get('id')
            name = resource.get('title')
            self.processor.add_spp(SPP(ldap=spp_ldap,name=name,id_in=spp_id))


# CLIENT
class CLIENT:
    """Клиент работающий в зависимости от режима (пост гет и тд)"""
    def __init__(self):  # Принимаем название комбинатора
        self._processor = Processor()
        self._session = None
        self._ssl_context = None
        self._certificate = None
        self._headers = None
        self._url = None
        self._req_mode = None
        self._post_data_pack = None
        self._current_spp = None
        self._url_template = None
        self._url_modifications = None

    async def _fetch_deal(self,url, post_data,spp):
        if self._req_mode == "post":
            async with self._session.post(url, headers=self._headers, json=post_data) as response:
                return await self._process_response(response, spp, post_data)
        elif self._req_mode == "delete":
            async with self._session.delete(url, headers=self._headers) as response:
                return await self._process_response(response)
        else:
            async with self._session.get(url, headers=self._headers) as response:
                return await self._process_response(response)

    async def _process_response(self, response, spp= None, post_data = None):

        text = None
        status = None
        if self._req_mode != "delete" :
            req_data = await response.json()
            text = await response.text()
            status = response.status
            self._processor.set_json(req_data)
        if self._req_mode == "post" : # для журнала
            self._processor.set_spp(spp)
            self._processor.set_text(text)
            self._processor.set_status(status)
            self._processor.set_post(post_data)
        self._processor.parse()

    async def main_asynch(self):
        await self._create_ssl_session(self._certificate)
        async with self._session:
            if self._req_mode == "post":  # если много post данных
                tasks = self._spps_posts()
            elif self._req_mode in ("delete", "get"):
                tasks = self._url_combiner()
            elif self._req_mode == "solo_get":   # Если одиночный запрос
                await self._fetch_deal(self._url,None, None)
                return
            await asyncio.gather(*tasks)  # Запускаем все задачи одновременно ВЫПОЛНЯЕМ ВСЕ (Коретины находятся в списках для структуры)

    def _url_combiner(self):
        tasks = []
        for modificatior in self._url_modifications:
            self._url = self._url_template.format(modificatior=modificatior)
            tasks.append(self._fetch_deal(self._url,None, None))  # Добавляем задачу в список И НЕ ВЫПОЛНЯЕМ ЕЕ
        return tasks

    def _spps_posts(self):
        tasks = []
        for spp in self._post_data_pack.SPPs.values():  # Распаковка чек
            for day in spp.post_table.values():
                for post in day:
                    tasks.append(self._fetch_deal(self._url,post,spp))  # Добавляем задачу в список И НЕ ВЫПОЛНЯЕМ ЕЕ
        return  tasks


    def set_request_mode(self, req_mode):
        self._req_mode = req_mode
        return self

    def set_url_modifications(self, url_modifications):
        self._url_modifications = url_modifications
        return self

    def set_url(self, url):
        self._url = url
        return self



    def set_url_template(self, url):
        self._url_template = url
        return self

    def set_post_data(self, data):
        self._post_data_pack = data
        return self

    def set_headers(self, headers):
        self._headers = headers
        return self

    def set_certificate(self, certificate):
        self._certificate = certificate  # Имя сертификата (он лежит в папке с программой)
        return self

    def set_processor_strategy(self,strategy):
        self._processor._strategy = strategy(self._processor) # Устанавливаем тип обработки, и передаем внутрь сам Processor для доступа к полям
        return self

    def get_data(self):
        return self._processor.get_data()

    async def _create_ssl_session(self, certificate):
        ssl_context = ssl.create_default_context()  # Создаем SSL-контекст
        ssl_context.load_verify_locations(cadata=certificate)
        connector = aiohttp.TCPConnector(ssl=ssl_context)  # Создаем TCP-коннектор с SSL
        self._session =  aiohttp.ClientSession(connector=connector)





class PostCreator:
    """Создает тела для post запросов в зависимости от статуса сотрудника, выходного и прочего """
    def __init__(self,main_data):  # Принимаем название комбинатора
        self.main_data = main_data
        self.response = None


    hour_min = main_world.hour_min
    hour_max = main_world.hour_max

    hour_vocation_start = "00:00"

    ldap_addition = 100000


    post_template= {
        "resourceId": None,
        "type": "TRAINING",   #  LUNCH   \    TASK_HANDLING
        "capacity": 1,
        "startedAt": None,
        "finishedAt": None   # Format : 2025-06-27T15:59:59.000Z
    }


    def activate(self):
        for spp in self.main_data.SPPs.values():
            if spp.post_table: # Если вообще расписание есть и статус сменный
                self._post_table(spp)

    def _post_table(self,spp):   # ОПТИМИЗИРОВАТЬ

        for key, time in spp.post_table.items():
            post_pack = []
            key_date =  TimeHelper.create_key_data(key)
            if len(time) > 1:

                #Создаем обеды и активности

                lunch_hour_start = TimeHelper.delta_time_hours(time[0], main_world.break_1)   # время перерывов
                lunch_hour_end =  TimeHelper.delta_time_hours(lunch_hour_start, 1)
                break_hour_start = TimeHelper.delta_time_hours(lunch_hour_start, main_world.break_2)
                break_hour_end = TimeHelper.delta_time_hours(break_hour_start, 1)

                post_br_1 = self.create_post("TASK_HANDLING",spp,lunch_hour_start,lunch_hour_end,key_date)
                post_br_2 = self.create_post("LUNCH",spp,break_hour_start,break_hour_end,key_date)
                post_pack.append(post_br_1)
                post_pack.append(post_br_2)

                # Создаем перекрытия для сменных
                if "сменный" in spp.status.lower():

                    time_min = TimeHelper.create_need_time(key_date,PostCreator.hour_min,start=True)  # создаю валидную строку времени запроса
                    time_end = TimeHelper.create_need_time(key_date, time[1],start=True)

                    # проверяю что границы не совпали(если совпали запрос не нужен)
                    if time_min != TimeHelper.create_need_time(key_date,time[0],start=True):
                        post_1 = self.create_post("TRAINING", spp, PostCreator.hour_min, time[0], key_date)
                        post_pack.append(post_1)
                    if time_end != TimeHelper.create_need_time(key_date, PostCreator.hour_max,start=True):
                        post_2 = self.create_post("TRAINING",spp, time[1], PostCreator.hour_max, key_date)
                        post_pack.append(post_2)

                # Работа с доп линией.
                if "(д)" in spp.status.lower():
                    pass

                spp.post_table[key] = []
                spp.post_table[key].extend(post_pack)

            else: # Чтобы обработать не время (В \ от \ ДВ \ б)
                if time[0].lower() == "от" or time[0].lower() == "дв" or time[0].lower() == "б":
                    time_min = TimeHelper.create_need_time(key_date, PostCreator.hour_vocation_start,start=True)
                    key2_date = TimeHelper.minus_day(time_min)
                    post_1 = self.create_post("VACATION", spp, PostCreator.hour_vocation_start, PostCreator.hour_vocation_start,key2_date,key_date)
                    spp.post_table[key] = [post_1]
                else:
                    spp.post_table[key] = []


    @staticmethod
    def copy_template():
        return copy.deepcopy(PostCreator.post_template)


    @staticmethod
    def create_post(type_blackout,spp,time_start,time_end,key,key2=None):
        time_start_format = TimeHelper.create_need_time(key, time_start, start=True)
        key_for_time_end = key2 if key2 is not None else key  # Возможность передать 2й ключ
        time_end_format = TimeHelper.create_need_time(key_for_time_end, time_end)
        new_dict = copy.deepcopy(PostCreator.post_template)
        new_dict["type"] = type_blackout
        new_dict["resourceId"] = spp.id_in
        new_dict["startedAt"] = time_start_format
        new_dict["finishedAt"] = time_end_format
        return new_dict



class AutoSchedule:
    
    def __init__(self,main_client):  # Принимаем название комбинатора
        self.main_client = main_client
        self.main_data = main_client.get_data()
    
    def _create_schedule_mode(self, ldap=None,start=None,end=None):
        self.main_client.set_url(main_world.url_eq_get). \
                       set_certificate(cert_1). \
                       set_headers(headersEQ). \
                       set_processor_strategy(Processor.EqRequester). \
                       set_request_mode("solo_get")
        asyncio.run( self.main_client.main_asynch())
    
        GoogleSheetCore(self.main_data).read_table()
        poster_maker = PostCreator(self.main_data)
        poster_maker.activate()
    
        self.filter_spps()
    
        if ldap and start and end:
             self.test_request(ldap,start,end)
        elif start and end:
            self.request_all_by_data(start,end)

        self.main_client.set_url(post_blackout). \
                       set_headers(post_bl_headers). \
                       set_request_mode("post"). \
                       set_post_data(self.main_data). \
                        set_processor_strategy(Processor.PostRequester)
        asyncio.run(self.main_client.main_asynch())
    
        self.create_log()
    

    
    def test_request(self, ldap, start, end):
        if isinstance(self.main_data.SPPs, dict):
            spp_1 = self.main_data.SPPs[ldap]
            self.main_data.SPPs = {ldap : spp_1}
            spp_1.post_table = self.days_interval(spp_1.post_table, start,end)

    def request_all_by_data(self, start, end):
        if isinstance(self.main_data.SPPs, dict):
            for spp in self.main_data.SPPs:
                spp_current = self.main_data.SPPs[spp]
                spp_current.post_table = self.days_interval(spp_current.post_table, start, end)


    def create_log(self):
        if isinstance(self.main_data.SPPs, dict):
            for spp in self.main_data.SPPs.values():
                if spp.errors.items():
                    errors_str = "\n".join(f"{key}: {value}" for key, value in spp.errors.items())
                    logging.error(f"У СПП - {spp.name} не вышло перекрыть : \n{errors_str} ")
    
    
    
    def delete_schedule_mode(self, ldap=None,start=1,end=None):
    
        day_of_month_modifications = TimeHelper.get_all_days(month,start,end)
        data = self.main_data
        self.select_spp_for_clearing(data,ldap)
    
        self.main_client.set_url_template(main_world.url_eq_group_get). \
            set_certificate(cert_1). \
            set_headers(headersEQ). \
            set_processor_strategy(Processor.EqDelRequester). \
            set_url_modifications(day_of_month_modifications). \
            set_request_mode("get")
        asyncio.run(self.main_client.main_asynch())
    
        ids = self.main_data.blackout_id
    
    
        self.main_client.set_url_template(delete_blackout). \
            set_processor_strategy(Processor.PassREQ). \
            set_url_modifications(ids). \
            set_request_mode("delete")
        asyncio.run(self.main_client.main_asynch())
    
    def filter_spps(self):
        if isinstance(self.main_data.SPPs, dict):
            keys_to_delete = []
            for key, spp in self.main_data.SPPs.items():
                if not (spp.post_table or spp.status): # Удаляем спп без статуса или таблицы пост
                    keys_to_delete.append(key)
            for key in keys_to_delete:
                del self.main_data.SPPs[key]

    def check_custom_mode(self, mode):

        if mode == "очистка":
            self.delete_schedule_mode()
            return
        elif mode == "создание":
            self._create_schedule_mode()
            return

        result = self.split_mode(mode)
        mode = result["mode"]
        start = int(result.get("start"))
        end = int(result.get("end"))
        ldap = None
        if result.get("ldap"):
            ldap = int(result.get("ldap"))

        if mode == "создание общий":
            self._create_schedule_mode(start=start, end=end)
        elif mode == "создание персональный":
            self._create_schedule_mode(ldap=ldap, start=start, end=end)
        elif mode == "очистка общий":
            self.delete_schedule_mode(start=start, end=end)
        elif mode == "очистка персональный":
            self.delete_schedule_mode(ldap=ldap, start=start, end=end)
        else:
            return
    
    
    @staticmethod
    def select_spp_for_clearing(data,ldap):
        if ldap:
            data.delete_spp = ldap

    @staticmethod
    def days_interval(post_table, start, end):
        new_dict = {}
        for key, value in post_table.items():
            if start <= int(key) <= end:
                new_dict[key] = value
        return new_dict
    
    @staticmethod
    def split_mode(mode) -> dict | None:
        result = mode.split(" ")
        if len(result) not in (3, 4): return None
    
        mode = result[0]
        if len(result) == 3:
            start = result[1]
            end = result[2]
            mode = mode + " общий"
            return  {
                "start": start,
                "end": end,
                "mode": mode
            }
        else:
            ldap = result[1]
            start = result[2]
            end = result[3]
            mode = mode + " персональный"
            return  {
                "ldap": ldap,
                "start": start,
                "end": end,
                "mode": mode
            }
    

def spp_point_main_funktion(): # Основная функция

    mode = input(f"{instruction}\n")
    print(f"VERSION {version}")
    main_client =  CLIENT()
    auto_schedule = AutoSchedule(main_client)
    auto_schedule.check_custom_mode(mode)
    








