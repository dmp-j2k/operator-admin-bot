FROM python:3.11
LABEL authors="Shebik"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

ENV PYTHONPATH=/app

RUN chmod +x ./start.sh
CMD ["./start.sh"]

