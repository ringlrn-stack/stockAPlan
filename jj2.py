import tushare as ts
import pandas as pd
import os
import time
from datetime import datetime, timedelta

# 1. 基础配置
TOKEN = os.getenv("TUSHARE_TOKEN")
if not TOKEN:
    print("【错误】未找到 Token，请检查 GitHub Secrets 或环境变量")
    exit()

# 修改提示信息
print("启动【月度竞价妖股扫描】(策略: 量比>=7 & 金额>=2700万, 需二次确认)...")
pro = ts.pro_api(TOKEN)

# 结果保存文件名
OUTPUT_FILE = f"double_confirm_auction_{datetime.now().strftime('%Y%m%d')}.xlsx"

def get_now_bj():
    """获取北京时间 (UTC+8)"""
    return datetime.utcnow() + timedelta(hours=8)

def get_trading_days(days_count=30):
    """
    获取最近 N 天的交易日列表
    注意：我们需要多取 1 天作为起始日的对比基数
    """
    now_bj = get_now_bj()
    end_str = now_bj.strftime('%Y%m%d')
    # 放宽范围以确保扣除节假日后天数足够
    start_str = (now_bj - timedelta(days=days_count * 2 + 15)).strftime('%Y%m%d')
    
    try:
        df = pro.trade_cal(exchange='SSE', start_date=start_str, end_date=end_str, is_open='1')
        if df.empty: return []
        dates = df.sort_values(by='cal_date', ascending=True)['cal_date'].tolist()
        # 截取最近 N+1 天
        return dates[-(days_count + 1):]
    except Exception as e:
        print(f"获取交易日历失败: {e}")
        return []

def get_stock_basic():
    """获取全市场股票列表"""
    print("📋 正在拉取全市场股票名单...")
    try:
        df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
        return df
    except Exception as e:
        print(f"股票列表获取失败: {e}")
        return pd.DataFrame()

def fetch_daily_auction(date_str, stock_codes):
    """
    批量拉取竞价数据
    """
    print(f"📥 扫描 [{date_str}] 全市场竞价...", end="")
    all_df = []
    chunk_size = 800 # 5100积分权益，单次拉取量大
    
    start_t = time.time()
    for i in range(0, len(stock_codes), chunk_size):
        chunk = stock_codes[i:i+chunk_size]
        codes_str = ",".join(chunk)
        try:
            df = pro.stk_auction(ts_code=codes_str, trade_date=date_str)
            if not df.empty:
                all_df.append(df)
        except:
            pass
            
    if all_df:
        full_df = pd.concat(all_df)
        # 聚合去重，防止脏数据
        full_df = full_df.groupby('ts_code')['amount'].sum().reset_index()
        print(f" 耗时:{time.time()-start_t:.1f}s, 数据:{len(full_df)}条")
        return full_df
    
    print(" (无数据)")
    return pd.DataFrame()

def run_scanner():
    # 1. 准备基础数据
    df_basic = get_stock_basic()
    if df_basic.empty: return
    all_codes = df_basic['ts_code'].tolist()

    # 2. 获取时间窗口 (最近30个交易日)
    dates = get_trading_days(days_count=30)
    if len(dates) < 2:
        print("❌ 交易日数量不足")
        return
    
    print(f"📅 扫描区间: {dates[1]} 至 {dates[-1]} (共 {len(dates)-1} 天)")
    
    # 3. 初始化接力棒 (第1天仅作对比基数)
    prev_date = dates[0]
    df_prev = fetch_daily_auction(prev_date, all_codes)
    if df_prev.empty:
        print("❌ 起始日无数据，无法计算量比，任务终止")
        return
    df_prev = df_prev.rename(columns={'amount': 'amt_prev'})
    
    # 用于收集所有符合条件的原始记录
    raw_anomalies = []

    # 4. 滚动扫描
    for curr_date in dates[1:]:
        df_curr = fetch_daily_auction(curr_date, all_codes)
        
        if df_curr.empty:
            print(f"⚠️ {curr_date} 无数据，跳过")
            continue
            
        # 准备数据
        df_curr_calc = df_curr.rename(columns={'amount': 'amt_curr'})
        
        # 合并计算
        merged = pd.merge(df_curr_calc, df_prev, on='ts_code', how='inner')
        merged['ratio'] = merged['amt_curr'] / merged['amt_prev']
        
        # --- 核心筛选条件 (已修改) ---
        # 1. 竞价金额 >= 2700万 (27,000,000)
        # 2. 量比 >= 7
        daily_hits = merged[
            (merged['amt_curr'] >= 27000000) & 
            (merged['ratio'] >= 7)
        ].copy()
        
        if not daily_hits.empty:
            daily_hits['date'] = curr_date
            # 格式化
            daily_hits['今日竞价(万)'] = round(daily_hits['amt_curr'] / 10000, 2)
            daily_hits['昨日竞价(万)'] = round(daily_hits['amt_prev'] / 10000, 2)
            daily_hits['量比'] = round(daily_hits['ratio'], 2)
            
            # 暂存数据 (ts_code, date, values...)
            raw_anomalies.append(daily_hits)
            print(f"   🔥 {curr_date}: 发现 {len(daily_hits)} 只异动股")
        else:
            print(f"   ( {curr_date}: 无满足条件股票 )")
            
        # 传递接力棒：今日变昨日
        df_prev = df_curr_calc.rename(columns={'amt_curr': 'amt_prev'})

    # 5. 二次确认筛选
    print("\n🔍 正在执行【二次确认】逻辑...")
    
    if raw_anomalies:
        df_all = pd.concat(raw_anomalies)
        
        # 统计每只股票出现的次数
        counts = df_all['ts_code'].value_counts()
        
        # 筛选出现次数 >= 2 的股票代码
        valid_codes = counts[counts >= 2].index.tolist()
        
        print(f"   - 原始异动股数: {len(counts)}")
        print(f"   - 二次确认股数: {len(valid_codes)} (出现 >= 2次)")
        
        if valid_codes:
            # 提取有效记录
            final_df = df_all[df_all['ts_code'].isin(valid_codes)].copy()
            
            # 关联中文名称
            final_df = pd.merge(final_df, df_basic, on='ts_code', how='left')
            
            # 添加“出现次数”列
            final_df['30天内次数'] = final_df['ts_code'].map(counts)
            
            # 排序：先按代码聚类，再按日期排序
            final_df = final_df.sort_values(by=['ts_code', 'date'], ascending=[True, True])
            
            # 整理列顺序
            cols = ['ts_code', 'name', '30天内次数', 'date', '今日竞价(万)', '昨日竞价(万)', '量比']
            final_df = final_df[cols]

            # 导出
            final_df.to_excel(OUTPUT_FILE, index=False)
            print(f"\n🎉 成功！已生成报表: {OUTPUT_FILE}")
            print("💡 请在 GitHub Action 的 Summary 页面下载 Artifacts 查看。")
            
        else:
            print("\n❌ 遗憾：虽有单日异动，但无股票满足【二次确认】条件。")
    else:
        print("\n❌ 遗憾：30天内未发现任何符合基础条件的异动。")

if __name__ == "__main__":
    run_scanner()
