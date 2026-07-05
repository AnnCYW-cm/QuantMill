# 🏭 QuantMill

**一个会自己拆穿自己的诚实量化平台** —— 从多市场数据 → 因子 → 模型 → 组合 → 执行,每一步都内建**抗过拟合的可信度检验**(DSR/PBO)。它不给你看漂亮回测就让你上头,而是当面告诉你"这个策略到底成不成立"。

> An honest, full-chain open-source AI quant platform for **HK / US / A-share**:
> data → factors → cross-sectional selection → backtest → **built-in credibility checks** →
> cross-market validation → forward-bias quantification.

!!! warning "诚实声明 / Honest disclaimer"
    这是**研究与教育框架,不是交易系统**。经平台自己的可信度层反复拷问,结论是:
    复杂 ML 排名模型是过拟合幻觉;简单价值/动量/低波因子组合是"真但弱"的边际
    (跨 A股/港股都为正、DSR 0.989,但档内超额仅 ~0.2–0.7%/期)。
    **任何信号仅供研究,别拿真钱跟。** 详见 [研究纪要](RESEARCH_NOTES.md)。

## 30 秒上手 / Try it in 30s

```bash
pip install -e ".[dev,web]"
quantmill cross backtest --sample   # 内置样本,离线秒出选股回测
quantmill web                       # 起本地网页台
```

## 从这里读起 / Start here

- [**架构与 UML**](ARCHITECTURE.md) —— 分层架构 + 组件/类/时序图(Mermaid)
- [**研究纪要**](RESEARCH_NOTES.md) —— ML 幻觉 vs 稳健组合、跨市场验证、前视偏差量化的完整调查
- [**CLI 参考**](CLI.md) —— 全部命令
- [**产品设计**](PRODUCT_DESIGN.md) —— 定位、路线图、对标 Qlib

## 核心铁律 / Iron rules

1. **无未来函数**,用测试焊死。
2. **诚实优先**:回测默认配 DSR/PBO,永远显示 vs 基准。
3. **跨市场验证**:一个市场赚是运气,两个独立市场都赚才可能是真的。
4. **偏差要量化,不能藏**。
5. **简单胜过复杂**:能跨市场活下来的简单因子,胜过看着漂亮的黑箱 ML。

---

源码与 issue:[github.com/AnnCYW-cm/QuantMill](https://github.com/AnnCYW-cm/QuantMill) · MIT License
