# 部署配置

本目录包含 QQ 机器人（NapCat）相关的部署脚本与配置，与 Inkar-Suki 主项目配套使用。

## 目录结构

- `scripts/` — NapCat 启动脚本、看门狗及配置文件
- `napcat/` — NapCat 运行时配置（`napcat.json`）

## 使用说明

1. 将 `scripts/napcat.env.example` 复制为 `scripts/napcat.env`，填入 QQ 账号密码
2. 按需修改 `scripts/napcat-watchdog.conf` 中的路径与 QQ 号
3. 安装看门狗：`bash scripts/napcat-watchdog-install.sh`
4. 启动 NapCat：`bash scripts/napcat-start.sh`

> 注意：NapCat 本体与 QQ 客户端需自行安装，不包含在本仓库中。
