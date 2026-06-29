"""
统一日志工具模块
控制台输出 + 文件持久化，兼容 Windows GBK 编码
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 简洁格式（无 emoji，兼容 Windows 控制台）
CONSOLE_FORMAT = logging.Formatter(
    "%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
FILE_FORMAT = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def setup_app_logger(name: str = "outdoor_buddy") -> logging.Logger:
    """初始化应用日志器"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    # 控制台 handler — 简洁格式，INFO 级别
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(CONSOLE_FORMAT)
    logger.addHandler(console_handler)

    # 文件 handler — 详细格式
    app_handler = RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(FILE_FORMAT)
    logger.addHandler(app_handler)

    # 错误文件 handler
    error_handler = RotatingFileHandler(
        LOG_DIR / "error.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(FILE_FORMAT)
    logger.addHandler(error_handler)

    return logger


logger = setup_app_logger()