# 捕鱼大世界 - 卡密授权版多账户资源查询

## 启动卡密服务器

```bash
cd server
pip install -r requirements.txt
python run.py
```

也可以回到项目根目录运行：

```bash
set CARD_ADMIN_PASSWORD=你的管理员密码
set CARD_JWT_SECRET=随机长字符串
python -m server.main
```

服务器默认监听 `0.0.0.0:8000`，数据库生成在 `server/data/cards.db`。生产部署见 `server/README.md`。

## 启动管理端

```bash
python admin_app.py
```

登录后可以批量生成卡密、导出 CSV、停用/启用、解绑机器码。

## 启动用户客户端

```bash
python app.py
```

输入服务器地址和卡密，联网校验通过后进入多账户管理界面。左侧显示当前账号资源，右侧管理多个游戏账号，底部登录新账号会自动写入本机加密数据库。

## 测试

```bash
python -m pytest server/tests tests -q --basetemp=.pytest_tmp -p no:cacheprovider
```
