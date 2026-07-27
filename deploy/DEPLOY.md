# 部署到服务器（大陆服务器 + Cloudflare 隧道，免备案）

> 前提：域名已在 Cloudflare 接入并 **Active**（NS 已从阿里云改到 Cloudflare）。
> 本文命令以 Ubuntu + 用户名 `ubuntu`、应用目录 `/home/ubuntu/interview-radar` 为例，按需替换。

---

## 阶段 A：装环境 + 拉代码（在服务器上）

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv git rsync
cd ~ && git clone https://github.com/Nikka-ops/interview-radar.git
cd interview-radar && bash install.sh
```

## 阶段 B：把题库数据传上去（在你**本机**执行）

服务器只展示题库，不在上面抓取。把本机建好的题库同步过去（`SERVER_IP` 换成服务器公网 IP）：

```bash
rsync -avz corpus_cache/banks/ ubuntu@SERVER_IP:~/interview-radar/corpus_cache/banks/
# 想让网页显示小红书图片，再同步图片资源（约 230M，可选）
rsync -avz corpus_cache/xhs/ ubuntu@SERVER_IP:~/interview-radar/corpus_cache/xhs/
```

以后每次本机重建完题库，重跑这条 rsync 即可更新线上。

## 阶段 C：网页设为常驻服务（在服务器上）

```bash
# 拷贝 systemd 配置，先改里面的 User/路径/密码/DeepSeek key
sudo cp ~/interview-radar/deploy/interview-radar.service /etc/systemd/system/
sudo nano /etc/systemd/system/interview-radar.service   # 改标了 CHANGE_ME 的几处

sudo systemctl daemon-reload
sudo systemctl enable --now interview-radar
sudo systemctl status interview-radar --no-pager        # 看到 active(running) 即成功
# 本机自测（还没走隧道）：
curl -u admin:你的密码 http://127.0.0.1:8765/health
```

> 网页只绑 `127.0.0.1`，不对外开端口，公网全靠下面的隧道进来，更安全。

## 阶段 D：Cloudflare 隧道（在服务器上）

```bash
# 1) 装 cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared && sudo mv cloudflared /usr/local/bin/

# 2) 登录（打印一个链接，复制到浏览器里授权 interviewhelper.xyz）
cloudflared tunnel login

# 3) 建隧道（记下输出的 Tunnel ID 和 json 路径）
cloudflared tunnel create interview-radar

# 4) 把域名解析指向这条隧道（Cloudflare 会自动加一条 CNAME）
cloudflared tunnel route dns interview-radar interviewhelper.xyz

# 5) 放配置文件，改里面的 <TUNNEL_ID>
sudo mkdir -p /etc/cloudflared
sudo cp ~/interview-radar/deploy/cloudflared-config.yml /etc/cloudflared/config.yml
sudo nano /etc/cloudflared/config.yml     # 把 <TUNNEL_ID> 换成第 3 步的 ID

# 6) 隧道设为常驻服务（开机自启）
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared --no-pager
```

## 完成

浏览器打开 **https://interviewhelper.xyz** → 弹密码框 → 输入 `admin` / 你设的密码 → 进入网页。
Cloudflare 自动带 HTTPS，无需自己配证书；服务器不开任何入站端口。

---

## 日常维护

| 场景 | 命令 |
|------|------|
| 更新题库 | 本机重建后 `rsync ... corpus_cache/banks/`，无需重启服务 |
| 更新代码 | 服务器 `git pull && sudo systemctl restart interview-radar` |
| 改密码 | 编辑 `interview-radar.service` 的 `WEB_AUTH_PASS` → `daemon-reload` + `restart` |
| 看网页日志 | `journalctl -u interview-radar -f` |
| 看隧道日志 | `journalctl -u cloudflared -f` |

## 排错

- **网页 502/无法访问**：先 `systemctl status interview-radar`，再 `curl 127.0.0.1:8765/health`。
- **域名打不开**：`systemctl status cloudflared`；确认 Cloudflare 后台域名是 Active、DNS 里有那条 CNAME。
- **国内访问慢**：Cloudflare 免费版大陆线路一般，10 人自用可接受；要更快需给服务器正式备案走直连。
