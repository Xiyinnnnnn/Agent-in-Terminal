# AGENT IN TERMINAL

> give it a need, the terminal handles it.
> 给需求，终端自己搞定。

![license](https://img.shields.io/badge/license-MIT-1e90ff?style=flat-square)
![python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square)
![deps](https://img.shields.io/badge/dependencies-zero-2ea44f?style=flat-square)
![model](https://img.shields.io/badge/model-deepseek--v4--flash-8b5cf6?style=flat-square)
![platform](https://img.shields.io/badge/platform-linux-f59e0b?style=flat-square)
![size](https://img.shields.io/badge/size-11.4KB-d1d5db?style=flat-square)

超轻量终端内 AI Agent。单文件、零依赖、自然语言驱动 shell —— 说人话，它拆解任务、执行命令、交付结果。

## QUICK START

```bash
curl -fsSL https://raw.githubusercontent.com/Xiyinnnnnn/Agent-in-Terminal/main/install.sh | bash
```

首次运行输入 DeepSeek API Key：

- 输入不可见（getpass）
- 机器绑定加密落盘（`~/.config/term_agent/key.bin`）
- 唯一落盘项，不出现明文

## USAGE

```bash
# 命令行
python3 ~/.local/bin/term_agent/term_agent.py

# 或应用菜单搜索「终端智能体」双击
```

## ARCHITECTURE

```
+-------------------+      +---------------------------+
|     welcome()     | ---> |           main()          |
|  first-run key    |      |  loop: llm <-> tool_calls |
|  setup + encrypt  |      |  MAX_ROUNDS=30 soft cap  |
+-------------------+      +-------------+-------------+
                                         |
              +--------------------------+--------------------------+
              |                          |                          |
       +------v------+            +------v------+            +------v------+
       |    llm()    |            |  compress() |            | run_terminal |
       |  deepseek-  |            |  900K       |            |   the only   |
       |  v4-flash   |            |  summary    |            |   tool: exec |
       |  64K cap    |            |  chain      |            |   shell cmds |
       +------+------+            +------+------+            +------+------+
              |                          |                          |
              |                    +-----v-----+                    |
              +------------------->| build_ctx |<-------------------+
                                   | mem_hist  |
                                   +-----+-----+
                                         |
                         +---------------+---------------+
                         |                               |
                  +------v------+                 +------v------+
                  |  key store  |                 |   memory    |
                  | encrypt/dec |                 | ~/.config/  |
                  | _machine_   |                 | term_agent/ |
                  | seed        |                 |  *.md files |
                  +-------------+                 +-------------+
```

| 层 | 组件 | 职责 |
|---|---|---|
| ENTRY | `welcome()` | 首次运行引导，Key 加密入库 |
| CORE | `main()` | 主循环：LLM 对话、工具调用解析、结果回填 |
| LLM | `llm()` | DeepSeek 接口，`with_tools` 切换压缩/推理模式 |
| MEM | `compress()` / `build_context()` | 900K 阈值压缩，摘要链跨会话延续 |
| TOOL | `run_terminal()` | 唯一工具：全部能力收敛到 shell |
| SEC | `encrypt/decrypt_key()` | 机器指纹种子 + 加密，Key 不落明文 |

## NOTES

- 新终端 = 新对话
- 想改参数？直接对它说「修改你的程序参数」
- 压缩阈值 / 模型 / 上限写死在程序里，让它自己改

## LICENSE

MIT
