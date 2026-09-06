# Channel Manager（微信/QQ 遥控）

`channel/` 为现有 Agent 增加一层极轻量 Channel Manager：让本 Agent 能被 **微信私聊 / QQ私聊 / QQ群@** 遥控。

- 不改 `term_agent.py` 本体；每条独立消息按需新建一个 Agent 进程（并发不串会话）。
- Agent 如何向聊天发消息/文件：用 Shell 调 `channel-reply "文本"` / `channel-send-file "/绝对路径"`。
- 启动：`python3 channel/manager.py --serve`（默认 local 适配器，测试用 `--test "消息" [附件路径...]`）。
- 真实微信/QQ：在 `channel/config.json` 的 `wechat`/`qq` 配好 iLink / OneBot(NapCat/Lagrange) 端点后，把 `adapters` 改为 `["qq"]` 或 `["wechat"]`。
- 详见 `channel/config.example.json` 与各 adapter 文件头注释。

## Agent Channel 控制中心（桌面傻瓜入口）

`control/control.py` 在 Channel Manager 之上加一个**轻量控制层**（非新服务、非框架），只做：启动/停止/状态、微信QQ登录状态查看、多模态开关、看日志。

- 一键安装桌面入口（应用菜单出现 **Agent Channel**，Terminal 弹出管理界面）：
  ```bash
  cd ~/.local/bin/term_agent && ./install_desktop.sh
  ```
  > 脚本按自身位置定位项目，移动目录后重跑一次即可。
- 控制中心 `Exec` 指向 `control/control.py`（不是 manager.py），以后加功能无需改桌面入口。
- 运行状态：PID/日志存 `/tmp/agent-channel/`（不入库）；残留 PID 自动识别清理；已运行则拒绝重复启动。
- 停止优先 SIGTERM 正常退出，超时才 terminate，最后才 kill。
- 多模态开关持久化到 **现有** `channel/config.json`（唯一配置，不新建），只影响新任务，不打断进行中 Agent。
- 微信/QQ 登录态由各自 Adapter 负责（iLink / OneBot），控制中心只显示状态与接入指引，不保存任何 token。
- 命令行子命令（脚本/快捷用）：`control/control.py --status | --start | --stop`
