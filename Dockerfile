FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY config ./config
COPY data ./data
COPY reports ./reports
ENTRYPOINT ["apex-fpl"]
CMD ["run", "--scenario", "both", "--horizon", "6"]
