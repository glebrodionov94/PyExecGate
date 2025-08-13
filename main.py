import os
import re
import asyncio
import logging
from functools import lru_cache
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel
import importlib.util

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем FastAPI приложение
app = FastAPI()

# Константы
SCRIPTS_DIR = 'scripts'
SCRIPT_TIMEOUT = 300

# Модель для данных, передаваемых в POST-запросе
class MethodRequest(BaseModel):
    method: str  # Формат: "script_name.method_name"
    params: Dict[str, Any]

def is_script_name_safe(script_name: str) -> bool:
    """
    Проверяет, что имя скрипта состоит только из латинских букв, цифр и символа подчеркивания.
    Используется re.fullmatch для полного соответствия.
    """
    return bool(re.fullmatch(r"[a-zA-Z0-9_]+", script_name))

@lru_cache(maxsize=32)
def load_script(script_name: str) -> Any:
    """
    Загружает Python-скрипт из папки SCRIPTS_DIR и кэширует модуль для повторного использования.
    """
    if not is_script_name_safe(script_name):
        logger.error(f"Небезопасное имя скрипта: {script_name}")
        raise HTTPException(status_code=400, detail="Unsafe script name.")

    script_path = os.path.join(SCRIPTS_DIR, f"{script_name}.py")
    if not os.path.exists(script_path):
        logger.error(f"Скрипт '{script_name}' не найден по пути: {script_path}")
        raise HTTPException(status_code=404, detail=f"Script '{script_name}' not found.")

    try:
        spec = importlib.util.spec_from_file_location(script_name, script_path)
        if spec is None or spec.loader is None:
            raise HTTPException(status_code=500, detail="Error loading script.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        logger.info(f"Скрипт '{script_name}' успешно загружен.")
        return module
    except Exception as e:
        logger.error(f"Ошибка загрузки скрипта '{script_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Error loading script: {e}")

async def run_script_async(
    script_name: str, method_name: str, params: Dict[str, Any], timeout: int
) -> Any:
    """
    Асинхронно загружает модуль скрипта и выполняет указанный метод с переданными параметрами.
    Обрабатывает таймаут и ошибки вызова функции.
    """
    module = load_script(script_name)

    if not hasattr(module, method_name):
        logger.error(f"Метод '{method_name}' не найден в скрипте '{script_name}'.")
        raise HTTPException(status_code=404, detail=f"Метод '{method_name}' не найден в скрипте '{script_name}'." )

    method = getattr(module, method_name)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(method, **params), timeout=timeout
        )
        logger.info(f"Метод '{method_name}' из скрипта '{script_name}' выполнен успешно.")
        
        # Проверяем, является ли результат файлом в формате словаря
        if isinstance(result, dict) and 'content' in result:
            content = result.get('content')
            # Проверяем, что содержимое - bytes
            if not isinstance(content, bytes):
                logger.error("Содержимое файла должно быть типа bytes.")
                raise HTTPException(status_code=500, detail="File content must be bytes.")
            
            # Получаем метаданные файла
            filename = result.get('filename', 'file.bin')
            media_type = result.get('media_type', 'application/octet-stream')
            
            # Создаем заголовок для скачивания файла
            headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
            
            # Возвращаем ответ с файлом
            return Response(content=content, media_type=media_type, headers=headers)
        else:
            # Возвращаем обычный результат (будет преобразован в JSON)
            return result
            
    except asyncio.TimeoutError:
        logger.error(f"Время выполнения метода '{method_name}' из скрипта '{script_name}' истекло после {timeout} секунд.")
        raise HTTPException(status_code=408, detail="Script execution timed out.")
    except TypeError as e:
        logger.error(f"Ошибка при вызове метода '{method_name}': {e}")
        raise HTTPException(status_code=400, detail=f"Error calling method '{method_name}': {e}")
    except Exception as e:
        logger.error(f"Ошибка выполнения метода '{method_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Error executing method '{method_name}': {e}")

@app.post("/run")
async def run_method(
    request: MethodRequest, timeout: int = Query(SCRIPT_TIMEOUT, ge=1, le=300)
):
    """
    Обрабатывает POST-запрос для выполнения метода скрипта.
    Ожидается, что параметр 'method' имеет формат 'script_name.method_name'.
    """
    try:
        script_name, method_name = request.method.split(".")
    except ValueError:
        logger.error("Неверный формат метода. Ожидается 'script_name.method_name'.")
        raise HTTPException(status_code=400, detail="Invalid method format. Should be 'script_name.method_name'.")

    logger.info(f"Получен запрос на выполнение: {script_name}.{method_name} с параметрами: {request.params}")
    result = await run_script_async(script_name, method_name, request.params, timeout)
    #if result.get("error") is not None:  # Если есть поле "error" (даже пустое)
    #    raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
