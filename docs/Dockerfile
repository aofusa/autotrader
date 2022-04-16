FROM python:3.7-slim AS build-env
ADD src /app
# ADD requirements.txt /app
WORKDIR /app
RUN pip install --target=/app --no-cache-dir -r requirements.txt

FROM gcr.io/distroless/python3-debian10
COPY --from=build-env /app /app
WORKDIR /app

CMD ["autotrader.py"]