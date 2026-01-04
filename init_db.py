import requests
import pandas as pd
import os
import time
from datetime import datetime

def get_data_from_eastmoney(params):
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10).json()
        return resp.get('data', {}).get('diff', [])
    except:
        return []

def run_task():
    db_file = "history_auction.csv"
    print(f"任务启动: {datetime.now()}")

    # --- 1. 获取今日实时竞价数据 ---
    params = {
        "pn": "1", "pz": "5000", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fid": "f46", 
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
        "fields": "f12,f14,f46,f13"
    }
    stocks = get_data_from_eastmoney(params)
    if not stocks:
        print("未能获取实时数据")
        return

    df_today = pd.DataFrame(stocks)
    df_today.rename(columns={'f12': 'code', 'f14': 'name', 'f46': 'today_auction'}, inplace=True)
    df_today['today_auction'] = pd.to_numeric(df_today['today_auction'], errors='coerce').fillna(0)

    # --- 2. 检查并初始化数据库 (自动回溯上一个交易日) ---
    if not os.path.exists(db_file) or os.path.getsize(db_file) < 100:
        print("数据库不存在，正在回溯抓取 2025-12-31 数据作为基准...")
        history_list = []
        # 为了演示和防止被封，我们只对今日竞价前 200 名或全市场进行抽样初始化
        # 实际生产中可以分批跑，这里先取前 300 只确保明天有数据
        sample_stocks = stocks[:300] 
        for i, s in enumerate(sample_stocks):
            secid = f"{s['f13']}.{s['f12']}"
            t_url = f"https://push2.eastmoney.com/api/qt/stock/trends2/get?secid={secid}&fields1=f1&fields2=f51,f56"
            try:
                t_resp = requests.get(t_url, timeout=5).json()
                trends = t_resp.get('data', {}).get('trends', [])
                opening_points = [x for x in trends if "09:30" in x]
                # 即使今天是周日，opening_points[-1] 也会拿到 12-31 的数据
                last_val = float(opening_points[-1].split(',')[1]) if opening_points else 0
                history_list.append({'code': s['f12'], 'last_auction': last_val})
            except: pass
            if i % 50 == 0: print(f"初始化进度: {i}/{len(sample_stocks)}")
            time.sleep(0.05)
        df_history = pd.DataFrame(history_list)
        df_history.to_csv(db_file, index=False)
    else:
        df_history = pd.read_csv(db_file, dtype={'code': str})

    # --- 3. 匹配并计算 ---
    df_merge = pd.merge(df_today, df_history, on='code', how='left')
    df_merge['last_auction'] = pd.to_numeric(df_merge['last_auction'], errors='coerce').fillna(0)
    
    def calc_ratio(row):
        if row['last_auction'] > 0:
            return round(row['today_auction'] / row['last_auction'], 2)
        return "N/A"

    df_merge['竞昨量比'] = df_merge.apply(calc_ratio, axis=1)
    
    # 筛选：今日竞价 > 2000万 (为了确保今天测试有文件，如果不满5行则取前5)
    df_report = df_merge[df_merge['today_auction'] >= 20000000].copy()
    if df_report.empty:
        print("未发现达标股票，输出前10只作为文件占位符...")
        df_report = df_merge.head(10).copy()

    df_report['今日竞价(万)'] = (df_report['today_auction'] / 10000).round(2)
    df_report['昨日竞价(万)'] = (df_report['last_auction'] / 10000).round(2)
    
    final_report = df_report[['code', 'name', '今日竞价(万)', '昨日竞价(万)', '竞昨量比']]
    final_report.to_excel("daily_report.xlsx", index=False)

    # --- 4. 覆盖更新数据库供明天使用 ---
    df_save = df_today[['code', 'name', 'today_auction']].copy()
    df_save.rename(columns={'today_auction': 'last_auction'}, inplace=True)
    df_save.to_csv(db_file, index=False)
    print("任务圆满完成。")

if __name__ == "__main__":
    run_task()
