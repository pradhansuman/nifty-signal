# Nifty Signal — NAS Docker Setup
# Works on: Synology, QNAP, TrueNAS, Unraid, any Linux NAS with Docker

FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    yfinance \
    pandas \
    flask \
    requests \
    numpy

# Copy app files
COPY nifty_monitor.py .
COPY nifty_pipeline_v2.py .
COPY nifty_server.py .
COPY pwa_static/ ./pwa_static/

# Expose port
EXPOSE 5099

# Start the server
CMD ["python", "nifty_server.py"]
