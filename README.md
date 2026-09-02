# C# Concurrency Coach

`csharp-concurrency-coach` 是一个面向中文学习者的 Codex Skill，用于系统学习 C# 与 .NET 并发编程。

它覆盖从语言基础、Task/TPL、`async`/`await`、同步原语与取消机制，到 CLR 实现原理、内存模型、无锁算法和 Windows 诊断工具的渐进式学习路径。学习进度、练习结果和复习计划保存在学习项目中，可跨 Codex 任务继续。

安装后，可以在 Codex 中使用 `$csharp-concurrency-coach`，或直接说“开始学习 C# 多线程”来启动学习。

## 环境要求

- Windows PowerShell 5.1 或 PowerShell 7+
- Git
- Codex
- 建议安装 .NET 8 或更高版本的 SDK，以运行配套实验

## 推荐安装方式

在 PowerShell 中执行：

```powershell
iwr -UseB https://raw.githubusercontent.com/FreeGoStudio/multithreading-learning-skill/main/scripts/install-from-git.ps1 | iex
```

脚本会自动：

- 从 GitHub 下载或更新本仓库到临时目录。
- 安装 `csharp-concurrency-coach` Skill。
- 在覆盖已有版本前创建带时间戳的备份。
- 根据 `CODEX_HOME` 选择安装目录；未设置时使用 `%USERPROFILE%\.codex`。

安装完成后，请新建一个 Codex 任务，使新安装的 Skill 生效。可以输入：

```text
使用 $csharp-concurrency-coach 开始学习 C# 并发与多线程。
```

也可以直接输入：

```text
开始学习 C# 多线程
```

## 指定 Git 地址或分支

使用 fork、镜像或其他分支时，先下载安装脚本，再传入参数：

```powershell
$installer = Join-Path $env:TEMP "install-csharp-concurrency-coach.ps1"
iwr -UseB https://raw.githubusercontent.com/FreeGoStudio/multithreading-learning-skill/main/scripts/install-from-git.ps1 -OutFile $installer
powershell -ExecutionPolicy Bypass -File $installer `
  -RepoUrl "https://github.com/your-org/multithreading-learning-skill.git" `
  -Branch "main"
```

如不需要保留旧版本，可使用 `-NoBackup` 直接覆盖：

```powershell
powershell -ExecutionPolicy Bypass -File $installer -NoBackup
```

## 本地安装方式

如果已经克隆本仓库，请在仓库根目录执行：

```powershell
.\scripts\install-skill.ps1
```

默认安装到 `%USERPROFILE%\.codex\skills\csharp-concurrency-coach`。如果设置了 `CODEX_HOME`，则安装到 `$env:CODEX_HOME\skills\csharp-concurrency-coach`。

也可以显式指定 Codex 主目录：

```powershell
.\scripts\install-skill.ps1 -CodexHome "D:\path\to\.codex"
```

重复运行安装命令即可更新。默认情况下，原版本会备份到同一 `skills` 目录下：

```text
csharp-concurrency-coach.backup-<时间戳>
```

确认不需要备份时，可以执行：

```powershell
.\scripts\install-skill.ps1 -NoBackup
```

## 项目结构

```text
csharp-concurrency-coach/
├─ SKILL.md                 # Skill 入口与核心规则
├─ agents/                  # Codex 界面元数据
├─ assets/lab-template/     # 实验项目模板
├─ references/              # 课程、教学、存储与诊断说明
├─ scripts/                 # 学习记录和实验管理工具
└─ tests/                   # 自动化测试
scripts/
├─ install-from-git.ps1     # 从 Git 仓库安装或更新
└─ install-skill.ps1        # 从本地仓库安装
```

学习数据不会写入 Skill 安装目录，而是保存在学习项目的 `.csharp-concurrency-learning/` 目录中。
