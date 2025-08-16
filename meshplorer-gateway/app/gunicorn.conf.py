import multiprocessing
import logging

# 設定 Gunicorn 使用的 Worker 相關數量
workers = multiprocessing.cpu_count() * 2 + 1
threads = multiprocessing.cpu_count() * 2
bind = "0.0.0.0:80"
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 300

# 允許所有 forwarded IP，讓 Uvicorn 解析 X-Forwarded-For 相關資訊
forwarded_allow_ips = "*"

# 設定日誌輸出到標準輸出 stdout
loglevel = "info"
accesslog = "-"  # Gunicorn 的存取日誌輸出到 stdout
errorlog = "-"  # Gunicorn 的錯誤日誌輸出到 stdout

# 確保 Gunicorn handlers 設定正確
gunicorn_logger = logging.getLogger("gunicorn.error")
gunicorn_logger.setLevel(logging.INFO)

# 讓所有 handler 使用相同的格式
for handler in gunicorn_logger.handlers:
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
