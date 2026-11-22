FROM python:3.12-slim
WORKDIR /opt/veriflow
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd -m -u 10001 veriflow && mkdir -p /data && chown veriflow:veriflow /data
COPY --chown=veriflow:veriflow app ./app
COPY --chown=veriflow:veriflow data ./data
USER veriflow
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
