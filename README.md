# 匿邮（NIMAIL）

面向 iCloud“隐藏邮件地址”的单管理员邮箱管理系统。管理操作使用原生 Windows 桌面程序；通过 CDK 查看邮件使用独立网页。

## 当前实现

- 原生 Windows 管理端，不带浏览器地址栏
- 单管理员首次初始化与登录
- 连接本机服务器或远程 HTTPS 域名
- 使用当前电脑的 Windows 默认浏览器登录 iCloud，手动粘贴完整 Cookie，不读取 Apple ID 主密码
- 按“创建数量”自动批量创建隐藏邮箱
- 每个邮箱生成独立的随机 Apple 标签，不使用连续编号、日期或批次前缀
- 每个邮箱自动生成并持久化独立 CDK
- 实时显示批量任务进度、邮箱、CDK 和失败状态
- 批量结果导出为 TXT，每行使用 `隐藏邮箱----CDK取信网址` 格式
- 配置 iCloud IMAP，后台归集并解析隐藏邮箱收到的邮件
- 管理端默认不显示邮件，管理员主动点击后才加载
- `https://你的域名/c/CDK` 查看该 CDK 对应的最近邮件、详情和验证码
- CDK 轮换、本地记录删除、Apple 隐藏邮箱停用/删除
- 首封邮件后按自定义时长停用邮箱、清理邮件和失效 CDK
- 邮箱/CDK 期限可直接选择长期、7 天、3 天、1 天或自定义时长
- “服务器设置”中可随时修改公网域名，无需重装且不改变已有邮箱/CDK
- Windows DPAPI 加密保存 Apple Cookie、IMAP 应用专用密码和管理端会话

## 成品程序

- 一键安装包：[dist-installer/NIMAIL-Setup.exe](dist-installer/NIMAIL-Setup.exe)
- 管理端：[dist-desktop/NIMAIL-Admin.exe](dist-desktop/NIMAIL-Admin.exe)
- 服务器：[dist-server/NIMAIL-Server.exe](dist-server/NIMAIL-Server.exe)

所有成品均已包含 Python 和运行库，目标 Windows 电脑不需要另装开发环境。

一键安装包提供两种模式：

- **本机使用**：自动安装管理端、后台收信服务和开机任务，不开放公网端口。
- **服务器远程使用**：在本机管理的基础上安装 Caddy 自动证书网关，仅使用公网 443，并只开放 `/c`、静态资源和 `/api/public/c/*`；邮箱生成、删除、Apple Cookie、IMAP 与管理员接口保持服务器本机访问。80 端口已有 Nginx 时不会冲突。

## 本机首次运行

1. 启动 `dist-desktop/NIMAIL-Admin.exe`。连接本机地址时，管理端会自动启动同目录的 `NIMAIL-Server.exe`。
2. 服务器地址填写 `http://127.0.0.1:8788`。
3. 勾选“首次安装”，设置唯一管理员账号和密码。管理端会自动读取本机一次性初始化凭据，不需要手动复制密钥。
4. 在“服务器设置”中配置 iCloud IMAP；应用专用密码可临时切换显示，以便检查输入。
5. 点击“在默认浏览器打开 iCloud”，完成登录后复制完整 Cookie，回到管理端粘贴并验证保存。
6. 进入“批量创建”，填写数量和创建间隔，点击“开始自动创建”；Apple 标签由系统逐个随机生成。

单次任务允许创建 1～20 个，默认每批 5 个、间隔 30 秒。任务按顺序执行，每成功一个就立即保存邮箱与 CDK；遇到 Apple 登录失效、频率限制或安全验证时停止并保留已成功结果，批量页会显示 Apple 返回的停止原因，不绕过 Apple 风控。

## 远程部署边界

服务器进程只监听 `127.0.0.1:8788`，一键安装器会在服务器模式下配置 Caddy、自动申请/续期证书并开放 443。远程管理端只允许连接 HTTPS；公开访客只能访问 `/c/CDK` 和对应的只读邮件接口，管理接口需要管理员会话。不要把 8788 端口直接暴露到公网。

## 开发与验证

```powershell
.\.venv-server\Scripts\python.exe -m pytest -q tests tests_server
.\build_server_windows.ps1
.\build_desktop_windows.ps1
.\build_installer_windows.ps1
```

`install_admin.ps1` 可为管理端创建桌面和开始菜单快捷方式。

## 说明

iCloud 隐藏邮箱网页接口不是 Apple 公开 API，网页结构或内部接口变化后可能需要适配。iCloud IMAP 必须使用 Apple“应用专用密码”，不要在本软件输入 Apple ID 主密码。
