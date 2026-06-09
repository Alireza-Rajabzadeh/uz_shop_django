FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y gettext

RUN pip install --no-cache-dir -r requirements.txt





COPY . .

EXPOSE 8000