FROM docker.io/library/debian:12-slim
RUN apt-get update && apt-get install -y curl
CMD ["bash"]
