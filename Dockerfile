FROM python:3.12.0-alpine

WORKDIR /app
RUN apk update && apk upgrade
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip uv
RUN uv pip install --system -r requirements.txt

COPY . /app

EXPOSE 8000

CMD ["uvicorn",   "app:app", "--host", "0.0.0.0"]
