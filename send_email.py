import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta

# 1. 配置信息 (适配 163 邮箱)
# 163 的 SMTP 服务器是 smtp.163.com
# 端口通常使用 465 (SSL)
SMTP_SERVER = os.getenv("EMAIL_HOST", "smtp.163.com") 
SMTP_PORT = int(os.getenv("EMAIL_PORT", 465))

# 从 Secrets 获取账号密码
EMAIL_USER = os.getenv("EMAIL_USER")     # 你的 163 邮箱地址 (xxx@163.com)
EMAIL_PASS = os.getenv("EMAIL_PASS")     # 你的 163 授权码 (注意：不是登录密码！)
EMAIL_TO = os.getenv("EMAIL_TO")         # 收件人邮箱

def get_current_date():
    """获取当前北京时间日期字符串"""
    # UTC + 8
    now = datetime.utcnow() + timedelta(hours=8)
    return now.strftime("%Y%m%d")

def send_email():
    if not EMAIL_USER or not EMAIL_PASS or not EMAIL_TO:
        print("【错误】邮件配置缺失，请检查 GitHub Secrets")
        return

    # 2. 文件查找与重命名
    base_filename = "daily_report"
    date_str = get_current_date()
    files_to_send = []
    
    # 重命名 Excel
    if os.path.exists(f"{base_filename}.xlsx"):
        new_name_xlsx = f"竞价日报_{date_str}.xlsx"
        os.rename(f"{base_filename}.xlsx", new_name_xlsx)
        files_to_send.append(new_name_xlsx)
        print(f"📄 文件已重命名为: {new_name_xlsx}")
    
    # 重命名 CSV (如果有)
    if os.path.exists(f"{base_filename}.csv"):
        new_name_csv = f"竞价日报_{date_str}.csv"
        os.rename(f"{base_filename}.csv", new_name_csv)
        files_to_send.append(new_name_csv)

    if not files_to_send:
        print("⚠️ 未找到日报文件，跳过发送。")
        return

    # 3. 构造邮件
    msg = MIMEMultipart()
    msg['Subject'] = f"【量化日报】A股竞价异动监控 - {date_str}"
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_TO

    body_text = f"附件是 {date_str} 的全市场竞价异动监控报表 (Based on 163 Mail Service)。\n\n自动化脚本发送，请勿回复。"
    msg.attach(MIMEText(body_text, 'plain'))

    # 4. 添加附件
    for f_path in files_to_send:
        try:
            with open(f_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(f_path))
            part['Content-Disposition'] = f'attachment; filename="{os.path.basename(f_path)}"'
            msg.attach(part)
        except Exception as e:
            print(f"❌ 读取附件出错: {e}")

    # 5. 发送邮件 (163 SSL 发送)
    try:
        print(f"🚀 正在连接 163 服务器 ({SMTP_SERVER}:{SMTP_PORT})...")
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()
        print(f"✅ 邮件已成功通过 163 发送至 {EMAIL_TO}")
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        print("提示：请确认 163 邮箱已开启 POP3/SMTP 服务，并使用【授权码】而非登录密码。")

if __name__ == "__main__":
    send_email()
