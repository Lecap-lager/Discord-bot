# /app_config.py

class AppConfig:
    def __init__(self):
        self.prefixes = ['!']
        self.token = 'token' # 봇 토큰
        self.admin = int('admin_id')
        self.DB_FILE = "lane_stats.db"

app_config = AppConfig()