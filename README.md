# 🎮 Katabump-Renew
自动续期 Katabump 服务器，每 4 天定时运行。

## 🔐 Secrets 配置
**Settings → Secrets and variables → Actions → New repository secret** 添加以下变量：

| Secret 名 | 说明 | 示例 |
|---|---|---|
| `KATABUMP_ACCOUNT` | 🧾 Katabump 登录邮箱和密码，用英文逗号分隔 | `me@example.com,mypassword` |
| `KATABUMP_SERVER_ID` | 🖥 服务器 ID（URL 中的 `?id=` 后面的数字） | `233971` |
| `GOST_PROXY` | 🌐 Gost 代理地址 | `socks5://user:pass@1.2.3.4:1080` |
| `TG_BOT` | 📨 Telegram 推送，Chat ID 和 Bot Token 用英文逗号分隔 | `987654321,123456:AAFxxx` |
| `PRIVATE_REPO_TOKEN` | 🔑 有私库读取权限的 GitHub PAT | `github_pat_xxxxxx` |

## 📝 PRIVATE_REPO_TOKEN 生成方式
GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token (classic) → 勾选 `repo` + `workflow` → Generate token → 填入 Secret。
