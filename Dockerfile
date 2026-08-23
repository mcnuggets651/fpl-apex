FROM python:3.12.14-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.runtime.lock pyproject.toml README.md LICENSE ./
COPY src ./src

# No mutable dependency resolution: every installed package/build tool is exact.
RUN python -m pip install --no-cache-dir --no-deps -r requirements.runtime.lock \
 && python -m pip install --no-cache-dir --no-deps setuptools==84.0.0 wheel==0.48.0 \
 && python -m pip install --no-cache-dir --no-deps --no-build-isolation .

COPY config ./config
COPY data ./data
COPY reports ./reports

ENTRYPOINT ["apex-fpl"]
CMD ["run", "--scenario", "both", "--horizon", "6"]
