# Используем официальный Python образ в качестве базового
FROM python:3.12

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл с зависимостями requirements.txt в рабочую директорию
COPY requirements.txt /app/

# Устанавливаем зависимости из requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем файл приложения app.py и папку scripts
COPY main.py /app/
COPY config.py /app/
COPY scripts /app/scripts/

# Указываем, что контейнер будет слушать на порту 8000
EXPOSE 8000

# Запускаем приложение на FastAPI через uvicorn
CMD ["python", "main.py"]