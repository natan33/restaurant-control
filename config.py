from collections import namedtuple
import os
from datetime import timedelta
from pathlib import Path
import socket
import json
from dotenv import load_dotenv
import redis

from app.core.env import BaseConfig


Setup = namedtuple('Setup', [ 'config'])


def read_():
    file_path = fr"{Path(os.getcwd()) / '.cred_api.json' }"
    with open(file_path, mode="r+", encoding="utf-8") as r:
            return json.load(r)
    



 
class Config(BaseConfig):

    def __init__(self):
        super().__init__()

        self.SECRET_KEY = self.get_env_or_raise('SECRET_KEY')
        self.SQLALCHEMY_DATABASE_URI = self.get_env_or_raise('SQLALCHEMY_DATABASE_URI')
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False

        self.SESSION_TYPE = 'filesystem'
    
    @staticmethod
    def init_app(app):
        print("Initializing application!")
        pass
 
 
class DevelopmentConfig(Config):
    def __init__(self):
        super().__init__()

        self.SQLALCHEMY_DATABASE_URI = self.get_env_or_raise('SQLALCHEMY_DATABASE_URI')
        self.DEBUG = True
        
 
class TestingConfig(Config):  #ambient of testing
    def __init__(self):
        super().__init__()
        self.DEBUG = True
        self.TESTING = True
        self.SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:postgres@localhost:5432/postgres'
        self.DB_USER = 'postgres'
        self.DB_PASSWORD = 'postgres'
        self.DB_HOST = 'localhost'
        self.DB_PORT = '5432'
        self.DB_NAME = 'postgres'
        self.GLO_OB = ''
        self.UPLOAD_FOLDER = os.path.abspath('app/uploads')
        self.DOWNLOAD_LOG = os.path.abspath('app/static/downloads/logs')
        self.ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'xlsx', 'xls', 'doc', 'docx', 'zip', 'msg', 'rar', 'ppt', 'pptx'}
        self.MAX_CONTENT_LENGTH = 16 * 1024 * 1024
        self.PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)
        self.CACHE_TYPE = 'simple'
        self.CACHE_DEFAULT_TIMEOUT = 300
 
 
class ProductionConfig(Config):
    def __init__(self):
        super().__init__()
        self.DEBUG = False
        self.TESTING = False

        self.SQLALCHEMY_DATABASE_URI = self.get_env_or_raise("SQLALCHEMY_DATABASE_URI")

        self.DB_USER = self.get_env_or_raise("DB_USER")
        self.DB_PASSWORD = self.get_env_or_raise("DB_PASSWORD")
        self.DB_HOST = self.get_env_or_raise("DB_HOST")
        self.DB_PORT = self.get_env_or_raise("DB_PORT")
        self.DB_NAME = self.get_env_or_raise("DB_NAME")

        self.MAIL_USERNAME = self.get_env_or_raise("MAIL_USERNAME")
        self.MAIL_PASSWORD = self.get_env_or_raise("MAIL_PASSWORD")

        self.UPLOAD_FOLDER = os.path.abspath("app/uploads")
        self.DOWNLOAD_LOG = os.path.abspath("app/static/downloads/logs")

class ConfigSocket(BaseConfig):
    def __init__(self):
        super().__init__()
        self.cors_allowed_origins = self.get_env_or_raise('CORS_ALLOWED_ORIGINS')
        self.async_mode = self.get_env_or_raise('ASYNC_MODE')
        self.message_queue = self.get_env_or_raise('MESSAGE_QUEUE')  # corrigido typo


 
 
# Chave para inicilizacao das config no init
config = {
    'development': DevelopmentConfig(), # <--- Note os parênteses
    # 'testing': TestingConfig(),     # <--- Note os parênteses
    # 'production': ProductionConfig(),   # <--- Note os parênteses
    # 'default': DevelopmentConfig()
}
# setup =ConfiGrafh()

# setup_run_time = Setup(
#     config=ConfigSocket()
# )
