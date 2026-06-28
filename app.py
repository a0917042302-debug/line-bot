import os
from flask import Flask, request, abort
from google import genai

# 導入 LINE Messaging API SDK v3 規範套件
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

# 從環境變數讀取憑證，避免金鑰外洩
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 初始化 LINE 與 Gemini 客戶端
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

@app.route("/", methods=['GET'])
def index():
    return "Bot is running!", 200

@app.route("/callback", methods=['POST'])
def callback():
    # 取得 LINE 標頭的加密簽章
    signature = request.headers.get('X-Line-Signature', '')

    # 取得請求主體文字
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")

    # 驗證簽章並處理事件
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Check your channel token or secret.")
        abort(400)

    return 'OK', 200

# 當收到使用者的文字訊息時，觸發此函式
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_message = event.message.text
    
    try:
        # 呼叫 Gemini API 生成對話
        # justin新增測試訊息
        app.logger.info(f"真正準備呼叫 Gemini: message_id={event.message.id}, text={user_message}")
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_message,
        )
        reply_text = response.text
    except Exception as e:
        app.logger.error(f"Gemini API 錯誤: {e}")
        reply_text = "（機器人思緒打結中，請稍後再試）"

    # 將 AI 的回應傳回給 LINE 使用者
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )

if __name__ == "__main__":
    # 本地測試時啟動 5000 埠口
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)