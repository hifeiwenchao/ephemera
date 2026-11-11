FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Older ARM Docker VMs can advertise unsupported OpenSSL CPU instructions.
# Use portable crypto routines so MySQL 8 authentication can initialize reliably.
ENV OPENSSL_armcap=0
WORKDIR /srv
COPY backend/ backend/
RUN pip install --no-cache-dir ./backend
ENV HOST=0.0.0.0 PORT=8001
EXPOSE 8001
CMD ["python", "-m", "backend.app.app"]
