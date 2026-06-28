# 已合併 ai_studio_code 2.py 與 app_longer_reply(1).py
# 部署到 Render 時，請將此檔案命名為 app.py，Start Command 使用：gunicorn app:app

import os
import time
import logging
import sys
from flask import Flask, request, abort
from google import genai
from google.genai import types

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.messaging.exceptions import ApiException
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s: %(message)s")
app.logger.setLevel(logging.INFO)
print("程式已載入 app.py", flush=True)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not LINE_CHANNEL_ACCESS_TOKEN:
    app.logger.warning("缺少環境變數 LINE_CHANNEL_ACCESS_TOKEN")
if not LINE_CHANNEL_SECRET:
    app.logger.warning("缺少環境變數 LINE_CHANNEL_SECRET")
if not GEMINI_API_KEY:
    app.logger.warning("缺少環境變數 GEMINI_API_KEY")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

processed_message_ids = {}
MESSAGE_TTL_SECONDS = 3600
MAX_PROCESSED_IDS = 10000


def cleanup_processed_message_ids():
    now = time.time()
    expired_ids = [mid for mid, ts in processed_message_ids.items() if now - ts > MESSAGE_TTL_SECONDS]
    for mid in expired_ids:
        processed_message_ids.pop(mid, None)

    if len(processed_message_ids) > MAX_PROCESSED_IDS:
        sorted_items = sorted(processed_message_ids.items(), key=lambda item: item[1])
        for mid, _ in sorted_items[: len(processed_message_ids) - MAX_PROCESSED_IDS]:
            processed_message_ids.pop(mid, None)


GEMINI_MODEL = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = """
# Role and Core Persona
你現在是聖經中的先知——【摩西（Moses）】。你正在帶領希伯來同胞與夥伴們經歷神蹟、逃離埃及法老的權勢。

- 說話語氣：必須極其「莊嚴」、「神聖」、「充滿歷史厚重感」與「權威感」。
- 常用詞彙：可使用「看哪」、「耶和華如此說」、「我屬神的夥伴啊」、「莫要疑惑」等具有聖經敘事感的詞彙。
- 嚴禁使用：現代網路流行語、輕浮用語、顏文字、Emoji。
- 不要為了營造口吻而每句都過度冗長；要清楚、可執行、完整。

# Mission & Anti-Spoiler Constraints
1. 你是 LINE 機器人的關卡引導者，只在玩家卡關、主動要求「提示」或輸入對應「關鍵字」時給予回應。
2. 【絕對禁止暴雷】：你擁有全知視角，但只能針對玩家當前所在的關卡給予暗示。
3. 嚴禁提及任何玩家尚未到達的後續災難、劇情、NPC 或謎題答案。
4. 【漸進式提示原則】：玩家要求提示時，先給予充滿神聖隱喻的劇情提示。
5. 絕對不能直接公布謎題答案或關鍵字。
6. 當玩家觸發謎題時，不要直接給答案，只能給鼓勵、確認與方向。

# Game Flow & Script Database

## [序章：尋找完整地圖]
- 流程：初始殘破地圖提示與商人對話 -> 觸發完整地圖任務。
- NPC 阿拉伯商人：抱怨沙塵暴，需要雜貨店老闆同意延期提交貨物的書信。
- NPC 雜貨店老闆：提到商人因沙塵暴難以提交貨物後，給予「同意延期交貨的書信」。
- 獎勵：商人拿到書信後給予完整地圖。
- 分流機制：地圖有編號 1, 2, 3 三個版本。
  - 編號 1：從【第一災：血災】開始。
  - 編號 2：從【第四災：蠅災】開始。
  - 編號 3：從【第七災：雹災】開始。

## [大主線 1：尼羅河畔與市井（第1~3災）]
### 1. 血災
- 觸發：對【宮廷術師1】說出密語：希伯來人的上帝。
- 引導：前往尼羅河碼頭找【船夫】。
- LINE 解謎：輸入「乾淨的水源」派發謎題。答案：1-1題 720、1-2題 LORD。獲得道具：泉水，關鍵字：活水江河。
- 關卡 1：前往河邊提交乾淨的水源給船夫，觸發現場關卡【巧拼渡河】。
- 通關獎勵：船夫交出信物，關鍵字：耶和華擊打河以後滿了七天。

### 2. 蛙災
- LINE 解謎：輸入「赫克特女神」派發謎題。答案：2-1題 Amphibians、2-2題 faith。
- 引導：前往地圖標示位置找【百姓】，說出關鍵字：耶和華使青蛙遍滿埃及地。
- 關卡 2：觸發現場關卡【蛙蛙蛙趴雞 趴雞】。
- 通關獎勵：百姓給予信物，關鍵字：埃及遍地佈滿了青蛙。
- 系統提示引導：法老反悔，心剛硬。引導玩家找到【亞倫】並說出：儘管上帝降下了蛙災，法老的心仍然剛硬。

### 3. 虱災
- LINE 解謎：對【亞倫】說出密語後，在 LINE 輸入「歌珊地安置」觸發解謎。答案：神的指頭。
- 引導：前往市集找【雜貨店老闆】說出：妳有看見米利暗嗎？
- 關卡 3：觸發現場關卡【除虱機】。
- 引導：通關後老闆指引方向，LINE 輸入「市集的東邊」，尋找【米利暗】並說出：耶和華在埃及地降下虱災。
- 通關獎勵：米利暗給予信物，關鍵字：神的榮耀在埃及地徹底顯明。
- 分流檢查：若還有未闖關卡，引導跨越地圖邊界前往【第二區】找【阿拉伯商人】；若無未闖關卡，觸發第一區破關結語。

## [大主線 2：埃及宮廷與商道（第4~6災）]
### 4. 蠅災
- 引導：與【阿拉伯商人】對話，LINE 輸入「購物清單」觸發解謎。答案：4-1題 13412133、4-2題 08200821。
- 引導：前往皇宮尋找【膳長】，說出關鍵字：耶和華已在埃及地降下了三災。
- 關卡 4：觸發現場關卡【捕蠅草】。
- 通關獎勵：獲得第四災信物，關鍵字：成群的蒼蠅。

### 5. 畜疫
- 引導：尋找【宮廷術師1】，說出關鍵字：耶和華降下畜疫在埃及。
- LINE 解謎：輸入「清點田間的牲畜」觸發解謎。答案：5-1題 6258193074、5-2題 GOSHEN。
- 引導：尋找【獸醫】，說出關鍵字：街上都是發狂的牛隻。
- 關卡 5：觸發現場關卡【牛牛保衛戰】。
- 通關獎勵：獲得信物，關鍵字：耶和華要分別以色列的牲畜。
- 引導：前往歌珊地尋找【希伯來長老】。

### 6. 瘡災
- LINE 解謎：長老給予提示，LINE 輸入「城防地圖」觸發解謎。答案：6-1題 11235813、6-2題 SERVANT。
- 引導：尋找【兵丁】，交還地圖並說出關鍵字：這是你遺落的城防地圖。
- 引導：兵丁中招，LINE 輸入「術士一點辦法都沒有」獲得提示。前往皇宮尋找【宮廷術師2】。
- 關卡 6：觸發現場關卡【止癢膏調配】。
- 通關獎勵：獲得術師認輸信物，關鍵字：耶和華不是邪術及假神可以勝過的。

## [大主線 3：諸天審判與絕境（第7~9災）]
### 7. 雹災
- 引導：對【宰相】說出關鍵字：重大的冰雹降下。
- 關卡 7：觸發現場關卡【躲避飛盤】。
- 通關獎勵：獲得信物，關鍵字：閃電烈火與巨雹。
- LINE 解謎：自動觸發。答案：7-1題 地圖、7-2題 8730062。

### 8. 蝗災
- 引導：尋找【農夫】，說出關鍵字：蝗蟲遮滿地面。
- 關卡 8：觸發現場關卡【定向越野】。
- 通關獎勵：獲得信物，關鍵字：蝗蟲吹入紅海。
- LINE 解謎：輸入答案「如墨黑暗」獲得劇情提示。

### 9. 黑暗災
- 引導：尋找最害怕的【宮廷守衛】，說出關鍵字：如墨的黑暗。
- 關卡 9：觸發現場關卡【黑暗之災】。
- 通關獎勵：獲得信物，關鍵字：唯有以色列人家中都有光亮。
- 分流檢查：若還有未闖關卡，回到起點，前往法老宮殿尋找【術師1】；若無未闖關卡，觸發最終完美通關結語。

# Response Evaluation Examples
User: 摩西，我們到尼羅河了，但不知道接下來要幹嘛，可以給我提示嗎？
Model: 看哪！這原本孕育埃及的尼羅河，如今在萬軍之耶和華的擊打下，已然化為滿目腥紅的血水。那在河畔唉聲嘆氣的船夫，正為他的生計與乾淨的水源發愁。我的夥伴啊，神的大能已在聊天中為你們預備了解謎的試煉，快在心中默念那四個字，向這絕望的船夫獻上「乾淨的水源」吧。莫要指望我直接降下答案，智慧隱藏在你們的腳步之中。

User: 聽說後面好像有蝗蟲跟黑暗災，你可以先告訴我那時候要找誰嗎？
Model: 住口，同胞啊！耶和華神的公義審判自有祂定規的時間與步伐。強求窺探未來的諸天，只會讓你的心如法老般陷入剛硬的迷霧。此時此刻，做好你當下的工，莫要窺探未臨到你的道路。

# Output Rules
- 每次回覆請控制在 120～220 個中文字以內。
- 一般回覆至少要有 3 句話。
- 回覆結構固定為：先用摩西口吻確認玩家進度，再用劇情描述加深沉浸感，最後給下一步方向。
- 必須是完整句子，不可停在半句。
- 結尾必須是「。」「！」「？」其中之一。
- 若內容太長，請自行濃縮，不可截斷句子。
- 不要輸出 Markdown、條列式清單或程式碼。
- 玩家只是回報進度時，請先確認他的進度，再給下一步方向。
- 不可直接公布謎題答案。
"""

# AI Studio 原始參數：temperature=0.75, max_output_tokens=300, top_p=0.95
# 實際部署保留較高 max_output_tokens，避免 LINE 回覆被截成半句；temperature 降低讓遊戲引導更穩定。
GENERATION_CONFIG = types.GenerateContentConfig(
    temperature=0.55,
    max_output_tokens=700,
    top_p=0.9,
    system_instruction=SYSTEM_INSTRUCTION,
)


def trim_to_complete_sentence(text, limit=4900):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_punctuation = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"), cut.rfind("!"), cut.rfind("?"))
    if last_punctuation > 0:
        return cut[: last_punctuation + 1]
    return cut.strip() + "。"


def is_incomplete_reply(text):
    if not text:
        return True
    text = text.strip()
    if len(text) < 15:
        return True
    if text[-1] not in "。！？!?」』":
        return True
    bad_endings = ["你已", "耶和華", "因為", "所以", "但是", "並且", "將會", "可以", "請你", "前往", "找到", "完成", "這", "那", "與", "和", "在", "向", "把", "將", "使"]
    return any(text.endswith(ending) for ending in bad_endings)


def is_too_short_reply(text):
    if not text:
        return True
    text = text.strip()
    sentence_count = sum(text.count(mark) for mark in ["。", "！", "？", "!", "?"])
    return len(text) < 70 or sentence_count < 2


def log_finish_reason(response, label="Gemini"):
    try:
        for index, candidate in enumerate(response.candidates or []):
            print(f"{label} candidate[{index}] finish_reason = {candidate.finish_reason}", flush=True)
    except Exception as e:
        print(f"無法讀取 {label} finish_reason: {e}", flush=True)


def generate_ai_reply(user_message):
    response = ai_client.models.generate_content(model=GEMINI_MODEL, contents=user_message, config=GENERATION_CONFIG)
    reply_text = (response.text or "").strip()

    print("Gemini 原始回覆 repr =", repr(reply_text), flush=True)
    print("Gemini 原始回覆長度 =", len(reply_text), flush=True)
    log_finish_reason(response, "Gemini first")

    if not reply_text:
        return "看哪，我屬神的夥伴啊，此刻風沙遮蔽了話語，請再向我說一次。"

    reply_text = trim_to_complete_sentence(reply_text)
    needs_retry = is_incomplete_reply(reply_text) or is_too_short_reply(reply_text)

    if not needs_retry:
        return reply_text

    print(f"偵測到回覆半句或過短，準備重試一次: {repr(reply_text)}", flush=True)

    retry_prompt = f"""
玩家輸入：「{user_message}」

請重新生成一則完整回覆。
規則：
1. 使用摩西引導員口吻。
2. 120～220 個中文字以內。
3. 至少 3 句話。
4. 先確認玩家進度，再用劇情描述加深沉浸感，最後給下一步方向。
5. 必須是完整句子。
6. 結尾必須是「。」「！」或「？」。
7. 不可停在半句。
8. 不可直接公布謎題答案。
9. 不要使用條列式或 Markdown。
"""

    retry_response = ai_client.models.generate_content(model=GEMINI_MODEL, contents=retry_prompt, config=GENERATION_CONFIG)
    retry_text = (retry_response.text or "").strip()

    print("Gemini 重試回覆 repr =", repr(retry_text), flush=True)
    print("Gemini 重試回覆長度 =", len(retry_text), flush=True)
    log_finish_reason(retry_response, "Gemini retry")

    retry_text = trim_to_complete_sentence(retry_text)
    if retry_text and not is_incomplete_reply(retry_text):
        return retry_text

    return "看哪，我屬神的夥伴啊！你的話語我已聽見，莫要疑惑，請照著當前的線索繼續前行。"


@app.route("/", methods=["GET"])
def index():
    print("有人打開首頁 /", flush=True)
    return "Bot is running!", 200


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    print("收到 LINE webhook", flush=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Check your channel token or secret.")
        abort(400)
    except Exception as e:
        print(f"Webhook 處理錯誤，但仍回 200 避免 LINE 重送: {e}", flush=True)
        app.logger.error(f"Webhook 處理錯誤，但仍回 200 避免 LINE 重送: {e}")

    return "OK", 200


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    message_id = event.message.id
    user_message = (event.message.text or "").strip()

    cleanup_processed_message_ids()
    print(f"收到訊息: message_id={message_id}, text={user_message}", flush=True)

    if not user_message:
        print(f"空白訊息，略過 Gemini: message_id={message_id}", flush=True)
        return

    if message_id in processed_message_ids:
        print(f"重複訊息，跳過 Gemini: message_id={message_id}", flush=True)
        return

    processed_message_ids[message_id] = time.time()

    try:
        print(f"真正準備呼叫 Gemini: message_id={message_id}, text={user_message}", flush=True)
        reply_text = generate_ai_reply(user_message)
    except Exception as e:
        print(f"Gemini API 錯誤: {e}", flush=True)
        app.logger.error(f"Gemini API 錯誤: {e}")
        reply_text = "（摩西暫時聽不清你的呼求，請稍後再試）"

    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_text)])
            )
        print(f"LINE 回覆成功: message_id={message_id}", flush=True)
    except ApiException as e:
        print(f"LINE reply 錯誤，不重新呼叫 Gemini: {e}", flush=True)
        app.logger.error(f"LINE reply 錯誤，不重新呼叫 Gemini: {e}")
    except Exception as e:
        print(f"未知 LINE 回覆錯誤: {e}", flush=True)
        app.logger.error(f"未知 LINE 回覆錯誤: {e}")


if __name__ == "__main__":
    print("使用 python app.py 啟動 Flask 本地伺服器", flush=True)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
