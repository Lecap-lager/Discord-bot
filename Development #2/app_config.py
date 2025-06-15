# /app_config.py

class AppConfig:
    def __init__(self):
        self.prefixes = ['!']
        self.token = 'token' # 봇 토큰
        self.admin = 'admin_id'

app_config = AppConfig()