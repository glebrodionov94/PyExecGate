# README

## FastAPI-сервис для безопасного запуска методов из внешних скриптов

Этот сервис поднимает HTTP API поверх папки `scripts/` и позволяет вызывать функции из ваших Python-скриптов по имени вида `script_name.method_name`.
Под капотом — FastAPI, загрузка модулей по `importlib`, кэширование через `lru_cache`, исполнение в отдельном потоке и строгая проверка имён. Есть поддержка отдачи файлов (через `Content-Disposition`) и таймаутов выполнения.

---

## Возможности

* 🚀 Вызов методов внешних скриптов по HTTP (`POST /run`)
* 🔒 Валидация имени скрипта (латинские буквы, цифры, подчёркивание)
* 🧠 Кэширование загруженных модулей (`lru_cache`)
* ⏱️ Таймаут выполнения (по умолчанию 300 сек, настраивается в query)
* 📎 Поддержка бинарной отдачи файлов из методов (скачивание)
* 🧵 Исполнение функций в отдельном потоке с асинхронной обёрткой
* 🪵 Логирование событий и ошибок
* 🧩 Простая структура: добавляйте скрипты в `scripts/your_script.py`

---

## Быстрый старт

### Требования

* Python 3.10+
* pip / venv
* (Опционально) Docker

### Установка

```bash
git clone https://github.com/glebrodionov94/scriptrunner.git
cd scriptrunner
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # если есть
# или:
pip install fastapi uvicorn pydantic
```

### Запуск

```bash
python3 main.py
```

Откройте интерактивную документацию:

* Swagger UI: `http://localhost:8000/docs`
* ReDoc: `http://localhost:8000/redoc`

---

## Как это работает

### Эндпоинт

`POST /run?timeout=<1..300>`

**Тело запроса (JSON)**

```json
{
  "method": "script_name.method_name",
  "params": { "key": "value", "another": 123 }
}
```

* `method` — строка вида `"имя_скрипта.имя_метода"`.
* `params` — словарь аргументов, которые будут распакованы как `method(**params)`.

### Структура проекта (минимум)

```
.
├── main.py
└── scripts/
    ├── __init__.py          # (не обязат.)
    ├── hello.py
    └── report.py
```

### Пример скрипта (возврат JSON)

`scripts/hello.py`:

```python
def greet(name: str, times: int = 1):
    return {"message": " ".join([f"Hello, {name}!" for _ in range(times)])}
```

Вызов:

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"method":"hello.greet","params":{"name":"World","times":2}}'
```

Ответ:

```json
{"message":"Hello, World! Hello, World!"}
```

### Пример скрипта (возврат файла)

Если метод возвращает **словарь** с ключом `content` (тип `bytes`), сервис отдаст файл на скачивание:

`scripts/report.py`:

```python
def build_csv():
    data = b"id,name\n1,Alice\n2,Bob\n"
    return {
        "content": data,                            # обязательно bytes
        "filename": "users.csv",                    # опционально (по умолчанию file.bin)
        "media_type": "text/csv"                    # опционально (по умолчанию application/octet-stream)
    }
```

Вызов:

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"method":"report.build_csv","params":{}}' \
  -OJ
```

Заголовок `Content-Disposition` будет установлен, файл сохранится как `users.csv`.

---

## Константы и конфигурация

* `SCRIPTS_DIR = "scripts"` — папка со скриптами.
* `SCRIPT_TIMEOUT = 300` — таймаут по умолчанию (сек). Можно переопределить query-параметром `timeout` в диапазоне `1..300`.

---

## Безопасность

* Имена скриптов строго валидируются: только `[a-zA-Z0-9_]`.
  Это защищает от попыток указать пути, точки, слэши и т. п.
* Модули загружаются **только** из `SCRIPTS_DIR`.
* Методы вызываются по имени, отсутствующие — 404.
* Код ваших скриптов исполняется в одном процессе Python. **Не запускайте непроверенный код.** При необходимости изолируйте в контейнере/сервисе.

---

## Исполнение и производительность

* Загрузка модуля кэшируется: `@lru_cache(maxsize=32)`.
* Метод вызывается через `asyncio.to_thread(...)` с `asyncio.wait_for(...)` — неблокирующая обёртка с таймаутом.
* Возврат значений:

  * Любые JSON-сериализуемые значения → обычный JSON-ответ.
  * Специальный формат `{ "content": <bytes>, "filename"?, "media_type"? }` → ответ с файлом.

---

## Коды ошибок

* `400 Bad Request`

  * Неверный формат `method` (ожидается `script.method`).
  * Ошибка вызова функции (например, неверные аргументы `TypeError`).
  * Небезопасное имя скрипта.
* `404 Not Found`

  * Скрипт не найден.
  * Метод в скрипте не найден.
* `408 Request Timeout`

  * Время выполнения истекло.
* `500 Internal Server Error`

  * Ошибка загрузки скрипта.
  * Исключение внутри метода скрипта.
  * Неверный формат файла (если `content` не `bytes`).

Примеры сообщений об ошибках возвращаются в поле `detail`.

---

## Логирование

Логи идут в stdout с уровнем `INFO`:

* Загрузка/кэширование скриптов
* Успешные вызовы
* Ошибки и таймауты
* Параметры входящих запросов (без скрытия — не передавайте чувствительные данные в `params`)

При необходимости настройте формат/уровень логирования в `main.py`.

---

## Советы по написанию скриптов

* Сигнатуры методов должны принимать **именованные** параметры (`**params` маппится по ключам).
* Обрабатывайте ошибки внутри скриптов и возвращайте информативные сообщения.
* Для файлов — возвращайте `bytes` в `content`. Если у вас строка, преобразуйте: `content = my_str.encode("utf-8")`.
* Долгие задачи — добавляйте свои таймауты/проверки прогресса. Помните про общий лимит `timeout`.

---

## Docker (опционально)

`Dockerfile` (минимальный пример):

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir fastapi uvicorn
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Сборка и запуск:

```bash
docker build -t scripts-runner .
docker run --rm -p 8000:8000 -v "$PWD/scripts:/app/scripts" scripts-runner
```

---

## Тестовые примеры запросов

### HTTPie

```bash
http POST :8000/run method=hello.greet params:='{"name":"Dev","times":3}'
```

### JavaScript (fetch)

```js
await fetch("/run", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({
    method: "hello.greet",
    params: { name: "JS", times: 2 }
  })
}).then(r => r.json());
```

### Python (requests)

```python
import requests

resp = requests.post(
    "http://localhost:8000/run",
    json={"method": "hello.greet", "params": {"name": "Python", "times": 2}},
    timeout=10,
)
print(resp.status_code, resp.json())
```

---

## FAQ

**Можно ли вызывать корутины (`async def`) из скриптов?**
Текущая реализация вызывает функции в отдельном **потоке** через `to_thread`, поэтому ожидается обычная синхронная функция. Если нужна поддержка `async def`, придётся доработать диспетчер.

**Как поменять папку со скриптами или дефолтный таймаут?**
Измените `SCRIPTS_DIR` и `SCRIPT_TIMEOUT` в `main.py`, либо прокиньте через переменные окружения и прочитайте их при старте.

**Почему мой файл не скачивается?**
Убедитесь, что возвращаете словарь с ключом `content` типа `bytes`. Для текста используйте `encode()`. Укажите корректный `media_type`.

---

## Контакты

Issues и предложения — через GitHub Issues в этом репозитории.