FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home pilot
COPY --chown=pilot:pilot app ./app
RUN mkdir /data && chown pilot:pilot /data
USER pilot
ENV SUPPORTPILOT_DATA=/data
EXPOSE 8020
CMD ["python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8020"]
