import requests
import pandas as pd
import os
from datetime import datetime

def run_task():
    db_file = "history_auction.csv"
    today_str = datetime.now().strftime('%Y-%m-%d')
    print(f"任务启动: {today_str}")

    # --- 1. 加载本地历史数据库 ---
    if os.path.exists(db_file):
        df_history = pd.read_csv(db_file, dtype={'code': str})
        print(f"成功加载历史数据库，包含 {len(df_history)} 条记录")
    else:
        df_history = pd.DataFrame(columns=['code', 'name', 'last_auction'])
        print("未发现历史数据库，今日将创建新库。")

    # --- 2. 获取今日实时竞价数据 (一次性请求) ---
    list_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "5000", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fid": "f46", 
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
        "fields": "f12,f14,f46" # 代码, 名称, 今日竞价额
    }
    
    try:
        resp = requests.get(list_url, params=params, timeout=10).json()
        stocks = resp['data']['diff']
        df_today = pd.DataFrame(stocks)
        df_today.rename(columns={'f12': 'code', 'f14': 'name', 'f46': 'today_auction'}, inplace=True)
        df_today['today_auction'] = pd.to_numeric(df_today['today_auction'], errors='coerce').fillna(0)
        
        # --- 3. 匹配昨日数据并计算量比 ---
        # 将今日数据与历史数据库合并 (Left Join)
        df_merge = pd.merge(df_today, df_history[['code', 'last_auction']], on='code', how='left')
        
        # 计算竞昨量比
        def calc_ratio(row):
            if row['last_auction'] and row['last_auction'] > 0:
                return round(row['today_auction'] / row['last_auction'], 2)
            return "N/A"

        df_merge['竞昨量比'] = df_merge.apply(calc_ratio, axis=1)
        
        # 筛选：今日竞价 > 2000万 且 排序
        df_report = df_merge[df_merge['today_auction'] >= 20000000].copy()
        df_report = df_report.sort_values(by="竞昨量比", ascending=False, key=lambda x: pd.to_numeric(x, errors='coerce'))

        # 整理输出表格
        df_report['今日竞价(万)'] = (df_report['today_auction'] / 10000).round(2)
        df_report['昨日竞价(万)'] = (pd.to_numeric(df_report['last_auction'], errors='coerce') / 10000).round(2)
        final_report = df_report[['code', 'name', '今日竞价(万)', '昨日竞价(万)', '竞昨量比']]
        
        # 保存 Excel 报告
        final_report.to_excel("daily_report.xlsx", index=False)
        print(f"今日报告已生成，筛选出 {len(final_report)} 只符合条件的股票")

        # --- 4. 关键：更新数据库，供明天使用 ---
        # 无论今天是否符合2000万，都记录所有股票的竞价额，作为明天的“昨日数据”
        df_save = df_today[['code', 'name', 'today_auction']].copy()
        df_save.rename(columns={'today_auction': 'last_auction'}, inplace=True)
        df_save.to_csv(db_file, index=False)
        print("数据库已更新，数据已持久化。")

    except Exception as e:
        print(f"运行出错: {e}")

if __name__ == "__main__":
    run_task()
