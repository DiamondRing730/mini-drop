# 独立演示场景

每条命令只运行一种负载、创建一个任务，并等待采集和分析全部完成。系统已经运行时只会切换
`minidrop-workload`，不会重复启动其他演示负载。

| 命令 | 任务名称 | 采集器 | 预期热点/结果 |
|---|---|---|---|
| `make demo-before` | `demo-cpu-before-baseline` | py-spy | 未缓存递归 `fib`，作为优化前基线 |
| `make demo-after` | `demo-cpu-after-optimized` | py-spy | 同一程序使用 `lru_cache`，`fib` 热点消失 |
| `make demo-numeric` | `demo-numeric-loops` | py-spy | `polynomial_loop` / `trigonometry_loop` |
| `make demo-io` | `demo-io-syscalls` | eBPF | read/write syscall 延迟分布 |

也可以使用统一入口：

```bash
make demo SCENARIO=cpu-before
make demo SCENARIO=cpu-after
make demo SCENARIO=numeric
make demo SCENARIO=io
```

## 优化闭环演示

依次执行，第一条完成后再执行第二条：

```bash
make demo-before
make demo-after
```

然后打开 `demo-cpu-after-optimized` 任务，在“可验证性能优化闭环”中选择
`demo-cpu-before-baseline`。本机实测两边均为 989 个样本，`fib` 自耗时占比从
74.22% 降至 0%，5/5 差分数值独立校验通过。
