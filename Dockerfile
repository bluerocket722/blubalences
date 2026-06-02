FROM python:3.11-slim
WORKDIR /app
COPY warmup_requirements.txt .
RUN pip install -r warmup_requirements.txt
COPY . .
CMD ["python3", "warmup_imap.py"]
