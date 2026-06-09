---
name: stock_price_history
description: 使用 yfinance 获取指定股票代码在指定日期范围内的历史股价明细，自动生成格式化表格（日期、星期、开盘/最高/最低/收盘价、涨跌幅、成交量）及统计摘要（最高/最低收盘价、期内总涨跌幅、总成交量）。支持任意粒度的日线数据查询。
tags:
- python
- yfinance
- stock
- finance
- data_analysis
---

## 技能：获取股票历史股价明细

### 前置条件
在沙箱环境中执行以下命令创建虚拟环境并安装依赖：
```bash
python -m venv /workspace/work/venv
/workspace/work/venv/bin/pip install yfinance pandas
```

### 参数说明
- `symbol` (str): 股票代码，如 "TSLA"（特斯拉）、"AAPL"（苹果）
- `start_date` (str): 开始日期，格式 "YYYY-MM-DD"
- `end_date` (str): 结束日期，格式 "YYYY-MM-DD"

### 标准执行步骤

1. **下载数据**：使用 yfinance.Ticker(symbol).history(start=start_date, end=end_date) 获取历史日线数据，包含 Open, High, Low, Close, Volume 字段。

2. **数据预处理**：
   - 按日期降序排列（最新的在前）
   - 计算每日涨跌幅：`df['Change%'] = df['Close'].pct_change(-1) * 100`
   - 填充首日涨跌幅为 "N/A"

3. **输出格式化表格**（示例格式）：
   日期 | 星期 | 开盘 | 最高 | 最低 | 收盘 | 涨跌幅 | 成交量

4. **输出统计摘要**：
   - 📅 数据区间（起始日 ~ 结束日）
   - 📈 最高收盘价及对应日期
   - 📉 最低收盘价及对应日期
   - 🏆 期内总涨跌幅 = (最新收盘 - 最旧收盘) / 最旧收盘 × 100%
   - 💰 期内总成交量（累加）

### 示例：查询特斯拉最近100个日历日（约70个交易日）股价

```python
import yfinance as yf
import pandas as pd

symbol = "TSLA"
# 最近100个日历日
end_date = "2026-06-09"
start_date = "2026-03-01"  # 约100天前

ticker = yf.Ticker(symbol)
df = ticker.history(start=start_date, end=end_date)

if df.empty:
    print("未获取到数据，请检查股票代码或扩大日期范围")
    exit()

df = df.sort_index(ascending=False)
df['Change%'] = df['Close'].pct_change(-1) * 100

# 输出表格表头
print(f'日期          星期   开盘      最高      最低      收盘      涨跌幅      成交量')
print('=' * 86)

# 逐行输出
for idx, row in df.iterrows():
    weekday = idx.strftime('%a')
    changepct = f"{row['Change%']:.2f}%" if pd.notna(row['Change%']) else "N/A"
    volume = f"{row['Volume']:,.0f}"
    print(f"{idx.strftime('%Y-%m-%d')}  {weekday}   "
          f"{row['Open']:<8.2f} {row['High']:<8.2f} {row['Low']:<8.2f} "
          f"{row['Close']:<8.2f} {changepct:<10} {volume}")

# 统计摘要（数据已降序排列，iloc[0]=最新，iloc[-1]=最旧）
newest_close = df['Close'].iloc[0]
oldest_close = df['Close'].iloc[-1]
total_return = (newest_close - oldest_close) / oldest_close * 100

print(f'\n📅 数据区间: {df.index[-1].strftime("%Y-%m-%d")} ~ {df.index[0].strftime("%Y-%m-%d")}')
print(f'📈 最高收盘价: ${df["Close"].max():.2f} ({df["Close"].idxmax().strftime("%Y-%m-%d")})')
print(f'📉 最低收盘价: ${df["Close"].min():.2f} ({df["Close"].idxmin().strftime("%Y-%m-%d")})')
print(f'🏆 期内总涨跌幅: {total_return:.2f}%')
print(f'💰 期内总成交量: {df["Volume"].sum():,.0f}')
print(f'📊 交易日数: {len(df)} 天')
```

### 注意事项
- 必须使用虚拟环境中的 Python 解释器执行：`/workspace/work/venv/bin/python script.py`
- 支持任意股票代码（如 "AAPL", "GOOGL", "MSFT", "AMZN" 等）
- 如需获取100个**交易日**而非日历日，建议将 start_date 向前推约140个日历日（约5个月）
- 如果数据点不足30个交易日，自动向前扩大 start_date 范围以确保足够的样本量
- 美股休市日（周末、法定假日）不会出现在数据中，无需额外处理
