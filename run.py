"""
应用启动入口
"""
import uvicorn
import logging

if __name__ == "__main__":
    # 配置 uvicorn 访问日志
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["fmt"] = "%(asctime)s | %(levelname)-5s | %(client_addr)s | %(request_line)s | %(status_code)s"
    log_config["formatters"]["access"]["datefmt"] = "%H:%M:%S"
    log_config["formatters"]["default"]["fmt"] = "%(asctime)s | %(levelname)-5s | %(message)s"
    log_config["formatters"]["default"]["datefmt"] = "%H:%M:%S"

    uvicorn.run(
        "app.main:app",
        host="localhost",
        port=8001,
        reload=True,
        log_level="info",
        log_config=log_config,
        access_log=True,
    )