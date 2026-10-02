# The image deskd runs from in production.
FROM gcr.io/distroless/python3-debian12:nonroot
WORKDIR /app
COPY deskd/ deskd/
COPY config/ config/
ENTRYPOINT ["python3", "-m", "deskd", "serve", "--host", "0.0.0.0", "--store", "/data/tickets.jsonl"]
