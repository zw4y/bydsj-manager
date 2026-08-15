# 卡密服务器部署说明

## 1. 购买轻量云服务器

推荐阿里云或腾讯云轻量应用服务器，配置 2 核 2G 即可，系统选择 Ubuntu 22.04。购买后在安全组/防火墙放行 80 和 443 端口（测试阶段可临时放行 8000）。

## 2. 方式一：Docker 部署

在服务器上安装 Docker 后执行：

```bash
docker build -f server/Dockerfile -t card-server .
docker run -d --name card-server \
  -p 8000:8000 \
  -v card-data:/data \
  -e CARD_ADMIN_PASSWORD=请改成强密码 \
  -e CARD_JWT_SECRET=请改成随机长字符串 \
  card-server
```

默认管理员账号是 `admin`，密码由 `CARD_ADMIN_PASSWORD` 指定。

## 3. 方式二：systemd 直接运行

```bash
python3 -m venv /opt/card-server/venv
/opt/card-server/venv/bin/pip install -r server/requirements.txt
cp -r server /opt/card-server/
```

创建 `/etc/systemd/system/card-server.service`：

```ini
[Unit]
Description=Card Server
After=network.target

[Service]
WorkingDirectory=/opt/card-server
Environment=CARD_DB_PATH=/opt/card-server/data/cards.db
Environment=CARD_ADMIN_PASSWORD=请改成强密码
Environment=CARD_JWT_SECRET=请改成随机长字符串
ExecStart=/opt/card-server/venv/bin/python -m server.main
Restart=always

[Install]
WantedBy=multi-user.target
```

然后：

```bash
systemctl daemon-reload
systemctl enable --now card-server
```

## 4. HTTPS（推荐）

安装 Caddy 后，在 `Caddyfile` 中配置：

```
card.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Caddy 会自动申请 Let's Encrypt 证书。客户端和管理端填写 `https://card.example.com` 作为服务器地址。

## 5. 数据安全

- 管理端需要明文展示卡密，因此数据库会保存卡密明文；请勿将数据库文件外传。
- 卡密支持“一月卡/季卡/半年卡/年卡”，到期时间从生成时刻自动后延。
- `CARD_ADMIN_PASSWORD` 和 `CARD_JWT_SECRET` 务必修改为强随机值。
