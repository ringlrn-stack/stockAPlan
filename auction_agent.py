import tushare as ts
import pandas as pd
import os
import time
from datetime import datetime, timedelta

# 1. 获取 Token
TOKEN = os.getenv("TUSHARE_TOKEN")
if not TOKEN:
    print("【错误】未找到 Token，请检查 GitHub Secrets 设置")
    exit()

print("启动【stk_auction 专用版】(利用 5100 积分获取官方竞价数据)...")
pro = ts.pro_api(TOKEN)

def get_strategy_dates():
    """
    智能日期逻辑 (北京时间):
    - 09:30 之前: 市场未开 -> 复盘模式 (对比 [昨] vs [前])
    - 09:30 之后: 竞价已出 -> 实战模式 (对比 [今] vs [昨])
    """
    # 修正 GitHub Actions 时区到北京时间
    now_bj = datetime.now() + timedelta(hours=8)
    print(f"🕒 当前北京时间: {now_bj.strftime('%Y-%m-%d %H:%M:%S')}")

    # 获取日历
    end_str = now_bj.strftime('%Y%m%d')
    start_str = (now_bj - timedelta(days=30)).strftime('%Y%m%d')
    
    try:
        cal = pro.trade_cal(exchange='SSE', start_date=start_str, end_date=end_str, is_open='1')
        print("pro.trade_cal")
        dates = cal.sort_values(by='cal_date', ascending=True)['cal_date'].tolist()
        print("cal.sort_values")
        
        if len(dates) < 3:
            return None, None, None

        # 阈值判定：09:30
        is_pre_market = now_bj.hour < 9 or (now_bj.hour == 9 and now_bj.minute < 30)

        if is_pre_market:
            print("🌙 盘前复盘模式：分析【上一交易日】数据...")
            return dates[-1], dates[-2], dates[-1] # 昨, 前, 昨(作为名单基准)
        else:
            print("☀ 盘中实战模式：分析【今日】竞价异动...")
            # 如果是16:00前，今天的日线榜单没出，用昨天的榜单圈股票
            ref_date = dates[-2] if now_bj.hour < 16 else dates[-1]
            return dates[-1], dates[-2], ref_date

    except Exception as e:
        print(f"日期计算出错: {e}")
        return None, None, None

def get_auction_data_batch(date_str, stock_list):
    """
    使用 stk_auction 接口批量获取竞价数据
    虽然 stk_auction 支持按日期取全市场，但为了防止超时或单次数据量过大，
    我们采用 500 只/批次 的稳健策略（5100积分速度极快）。
    """
    print(f"📥 正在拉取 {date_str} 的竞价数据 (stk_auction)...")
    all_df = []
    
    # 分批次查询，每次 500 只
    chunk_size = 500
    for i in range(0, len(stock_list), chunk_size):
        chunk = stock_list[i:i+chunk_size]
        codes_str = ",".join(chunk)
        
        try:
            # 接口：stk_auction
            # 参数：trade_date, ts_code
            df = pro.stk_auction(ts_code=codes_str, trade_date=date_str)
            if not df.empty:
                all_df.append(df)
        except Exception as e:
            print(f"批次请求异常: {e}")
    
    if all_df:
        return pd.concat(all_df)
    return pd.DataFrame()

def run_task():
    # 2. 确定日期
    target_date, compare_date, ref_list_date = get_strategy_dates()
    if not target_date:
        print("❌ 无法获取有效日期")
        return

    print(f"📅 分析区间: {target_date} (最新) vs {compare_date} (基准)")

    # 3. 圈定股票池 (活跃股前 800 名)
    # 5100积分能力强，我们把范围扩大到 800 只，防止漏网之鱼
    try:
        df_daily = pro.daily(trade_date=ref_list_date, fields='ts_code,name,amount')
        if df_daily.empty:
            print("⚠ 基准日无数据，尝试回溯一天...")
            prev_date = (datetime.strptime(ref_list_date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
            df_daily = pro.daily(trade_date=prev_date, fields='ts_code,name,amount')
        
        # 按成交额排序，取前 800 只
        df_daily = df_daily.sort_values(by='amount', ascending=False).head(800)
        target_codes = df_daily['ts_code'].tolist()
        print(f"✅ 已锁定核心池: {len(target_codes)} 只")

    except Exception as e:
        print(f"选股池获取失败: {e}")
        return

    # 4. 拉取竞价数据 (核心步骤)
    # 分别拉取 [目标日] 和 [对比日] 的 stk_auction 数据
    
    # 4.1 拉取今日(或目标日)
    df_curr = get_auction_data_batch(target_date, target_codes)
    # 4.2 拉取昨日(或对比日)
    df_prev = get_auction_data_batch(compare_date, target_codes)
    
    if df_curr.empty or df_prev.empty:
        print("❌ 未获取到完整的竞价数据，请检查日期或接口权限。")
        pd.DataFrame(columns=["代码"]).to_excel("daily_report.xlsx")
        return

    # 5. 数据清洗与计算
    print("🚀 正在计算量比与生成报告...")
    
    # 提取需要的字段: ts_code, amount
    # stk_auction 返回的 amount 单位通常是【元】
    df_curr_clean = df_curr[['ts_code', 'amount']].rename(columns={'amount': 'amt_curr'})
    df_prev_clean = df_prev[['ts_code', 'amount']].rename(columns={'amount': 'amt_prev'})
    
    # 合并
    merged = pd.merge(df_curr_clean, df_prev_clean, on='ts_code', how='inner')
    
    results = []
    for _, row in merged.iterrows():
        curr_amt = row['amt_curr']
        prev_amt = row['amt_prev']
        
        # 过滤门槛：2000万 (20,000,000)
        if curr_amt >= 20000000:
            # 找回股票名称
            name_row = df_daily[df_daily['ts_code'] == row['ts_code']]
            name = name_row['name'].values[0] if not name_row.empty else ""
            
            # 计算量比
            ratio = round(curr_amt / prev_amt, 2) if prev_amt > 0 else 0
            
            results.append({
                "代码": row['ts_code'],
                "名称": name,
                "日期": target_date,
                "今日竞价(万)": round(curr_amt / 10000, 2),
                "昨日竞价(万)": round(prev_amt / 10000, 2),
                "竞昨量比": ratio
            })

    # 6. 保存结果
    if results:
        final_df = pd.DataFrame(results).sort_values(by='竞昨量比', ascending=False)
        final_df.to_excel("daily_report.xlsx", index=False)
        final_df.to_csv("daily_report.csv", index=False, encoding='utf_8_sig')
        print(f"\n🎉 成功！基于官方 stk_auction 接口筛选出 {len(final_df)} 只股票。")
    else:
        print("\n未发现符合 2000万 门槛的股票。")
        pd.DataFrame(columns=["代码"]).to_excel("daily_report.xlsx")

if __name__ == "__main__":
    run_task()
