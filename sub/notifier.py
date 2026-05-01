"""
sub/notifier.py
Gmail による通知モジュール。

Gmail: HTML マップファイルをメールに添付して送信する
"""

import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from config import (
    GMAIL_ADDRESS,
    GMAIL_APP_PASSWORD,
)


# ======================================================================
# Gmail 通知
# ======================================================================

def send_email(
    to_address: str,
    subject: str,
    body: str,
    html_file_path: str = None,
) -> bool:
    """
    Gmail SMTP (App Password) でメールを送信する。
    html_file_path が指定されている場合、HTML ファイルを添付する。

    Returns:
        bool: 送信成功なら True
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("【Gmail】GMAIL_ADDRESS または GMAIL_APP_PASSWORD が未設定のためスキップします。")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = formataddr(("SUUMO通知Bot", GMAIL_ADDRESS))
    msg["To"]      = to_address
    msg.set_content(body)

    # HTML ファイルを添付
    if html_file_path and os.path.exists(html_file_path):
        with open(html_file_path, "rb") as f:
            filename = os.path.basename(html_file_path)
            msg.add_attachment(
                f.read(),
                maintype="text",
                subtype="html",
                filename=filename,
            )
        print(f"【Gmail】添付: {filename}")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
        print(f"【Gmail】送信成功 → {to_address}")
        return True
    except Exception as e:
        print(f"【Gmail】送信失敗: {e}")
        return False


# ======================================================================
# 通知まとめ関数
# ======================================================================

def notify_completion(
    property_type: str,   # "chuko" or "chintai"
    count: int,
    map_html_path: str,
    to_email: str = None,
) -> None:
    """
    スクレイピング完了後に Gmail で通知する。

    Args:
        property_type : "chuko"（中古マンション）または "chintai"（賃貸）
        count         : 検索結果件数
        map_html_path : 生成された HTML マップのパス
        to_email      : 送信先メールアドレス（None の場合は通知スキップ）
    """
    label = "中古マンション" if property_type == "chuko" else "賃貸物件"

    # ---- Gmail ----
    if to_email:
        subject = f"【SUUMO通知】{label} 検索完了 ({count}件)"
        body = (
            f"SUUMO {label} の検索が完了しました。\n\n"
            f"検索結果: {count}件\n"
            f"マップHTMLファイルを添付しています。\n"
            f"ブラウザで開いてご確認ください。\n\n"
            f"---\n"
            f"このメールは自動送信されています。"
        )
        send_email(
            to_address=to_email,
            subject=subject,
            body=body,
            html_file_path=map_html_path,
        )
