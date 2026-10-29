# api/main.py
import uvicorn
from fastapi import FastAPI



# 初始化应用实例
# app = create_app()

if __name__ == "__main__":
    #  uvicorn com.app:create_app --host 0.0.0.0 --port 5003 --workers 1
    uvicorn.run(
        "app:create_app",
        factory=True,
        host='0.0.0.0',
        port=5005
    )
