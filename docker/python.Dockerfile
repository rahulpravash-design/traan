# Shared image for api, mock-fleet and (with EXTRA=perception) the perception service.
FROM python:3.11-slim
WORKDIR /app
ARG EXTRA=""
COPY requirements.txt ./
COPY perception/requirements.txt perception/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$EXTRA" = "perception" ]; then pip install --no-cache-dir -r perception/requirements.txt; fi
COPY . .
ENV PYTHONUNBUFFERED=1
