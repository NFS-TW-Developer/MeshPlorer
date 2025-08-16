FROM python:3.12-slim

# 環境相關設定
RUN apt-get update && \
    apt-get install -y --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# PIP 相關設定
COPY requirements.txt .
RUN --mount=type=cache,target=~/.cache/pip \
    pip3 install -r requirements.txt

# APP 相關設定
WORKDIR /workspace
COPY . .

# 複製相關腳本
COPY entrypoint.sh /entrypoint.sh
COPY clean-tmp.sh /usr/local/bin/clean-tmp.sh
RUN chmod +x /entrypoint.sh /usr/local/bin/clean-tmp.sh

# 啟動相關設定
CMD ["/entrypoint.sh"]
