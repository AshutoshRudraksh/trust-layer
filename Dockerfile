FROM python:3.12-slim
WORKDIR /repo
COPY . .
RUN pip install --no-cache-dir -e ".[dev,mcp]"
CMD ["sh", "-c", "python -m pytest -q && python -m pyx.run check-eval --eval-sha256 73583998bfccc2dbb3831b5f2425e196a8505fe740bd0dac4e17dcb957c27ddb"]
