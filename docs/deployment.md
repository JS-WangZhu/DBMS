# 部署文档（基础版）

## 1. 环境准备

- OS: CentOS 7+ / Ubuntu 18.04+
- Python: 3.10+
- Node.js: 18+
- MySQL: 8.0+

## 2. 后端部署

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

设置 `.env`：

- `DATABASE_URL=mysql+pymysql://user:pass@127.0.0.1:3306/dbms_meta`
- `SECRET_KEY=...`
- `JWT_SECRET_KEY=...`
- `FERNET_KEY=...`
- `AUTH_MODE=local`
- `WECHAT_WEBHOOK_URL=...` (可选，备份失败企微通知)
- `SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD/SMTP_FROM/SMTP_TO` (可选，备份失败邮件通知)

初始化元数据库：

```bash
mysql -uroot -p dbms_meta < ../sql/schema.sql
```

启动：

```bash
flask --app app:create_app run -h 0.0.0.0 -p 5000
```

## 3. 前端部署

```bash
cd frontend
npm install
npm run build
npm run preview
```

生产建议将 `dist/` 交由 Nginx 托管，并反向代理 `/api` 到 Flask 服务。

## 4. 安全建议

- 启用 HTTPS。
- LDAP 连接使用 TLS。
- 定期轮换密钥。
- 限制备份目录访问权限。
