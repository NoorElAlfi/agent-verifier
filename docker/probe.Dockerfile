# Probe image: python:3.12-slim + pytest only. Run with --network none (see av/probes/sandbox.py).
FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==8.3.4
WORKDIR /work
