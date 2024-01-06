import os
import json
import openai
import mistune
from flask import Flask, flash, render_template, request

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
app.secret_key = 'chatbot-session-key'

@app.route("/", methods=("GET", "POST"))
def index():
    #HTTPメソッドが"POST"の場合
    if request.method == "POST":
        #過去の対話履歴を保持するもの(なければ"None")
        conversation_so_far = request.form.get('conversation_so_far', None)
        #ユーザーの入力を検知(なければ""(空)の文字列になる)
        user_message = request.form.get('user_message', '')
        #デフォルトのモデル設定("gpt-4"をデフォルトにしている)
        model = request.form.get('model', 'gpt-4')
        #フォームからapiキーを取得(無ければ環境変数から取得)
        key = request.form.get('key', os.getenv("OPENAI_API_KEY"))
        #APIキーを入力
        openai.api_key = key
        #system_prompt.txtに、システムのプロンプトを変更
        messages = [{"role": "system", "content": render_template('system_prompt.txt')}]

        #履歴を保持し、最新の対話を成立させるため(jsonで会話履歴を解析)
        if conversation_so_far and conversation_so_far != '':
            messages += parse_conversation(conversation_so_far)
        #ユーザーが新しいメッセージを投稿するたびに、対話メッセージリストに追加する
        if user_message != '':
            messages.append({"role": "user", "content": user_message})

        #エラー発生状態を管理するフラグを導入
        error_occurred = False
        #createメソッドの実行 エラーが出たい場合は各exceptで判断
        try:
            response = openai.ChatCompletion.create(
                model=model,             # change to gpt-3.5-turbo once function calling is included. As of 23 June, only 0613 has it.
                messages=messages,
                #functions=get_chatgpt_functions(),
                temperature=0.7,
            )
        except openai.error.RateLimitError as e:
            flash('OpenAI APIがリクエストの処理に対する利用制限(Rate Limit)に達したようです…', 'error')
            error_occurred = True
        #OpenAI APIが一時的なエラー状態にある場合に発生するエラー
        except openai.error.TryAgain as e:
            flash('現在サーバーが過負荷になっています。後でもう一度試してください…', 'error')
            error_occurred = True
        #OpenAI APIが一時的に利用不可状態にある場合に発生するエラー
        except openai.error.ServiceUnavailableError as e:
            flash('現在サーバーが過負荷になっています。後でもう一度試してください…', 'error')
            error_occurred = True
        #上記以外のエラーが発生した場合
        except Exception as e:
            flash('何か問題が発生しました。後でもう一度お試しください…', 'error')
            error_occurred = True

        #エラーがない場合の処理
        if not error_occurred:
            #レスポンスに 'function_call' 構造が含まれている場合、それを処理してメッセージを作成
            if response.choices[0]['message'].get('function_call'):
                messages.append({"role": "function", "name": response.choices[0]['message'].get('function_call')['name'],
                                 "content": execute_openai_function(response.choices[0]['message'].get('function_call'))
                                 })
            # 'function_call' 構造が含まれていない場合、APIの結果をメッセージに追加
            else:
                messages.append({"role": "assistant", "content": response.choices[0]['message']['content'].strip()})

        #対話メッセージをHTML変換し、それをフロントエンドに返す
        return render_template("index.html", conversation=messages_to_html(messages),
                               conversation_json=messages_to_json(messages))

    return render_template("index.html")

#/settingsのルーティング
@app.route('/settings', methods=('GET', 'POST'))
def settings():
    return render_template('settings.html')


def parse_conversation(conversation_so_far):
    return json.loads(conversation_so_far)


# システムプロンプトを除いて、メッセージのHTMLを作成
def messages_to_html(messages):
    html = ''
    for message in messages:
        #メッセージの役割"role"が、systemじゃない場合に実行する
        if message['role'] != 'system':
            message_content = mistune.html(message['content'])
            html += render_template('message.html', role=message['role'], content=message_content)
    return html


#メッセージをJSONに変換(systemプロンプトは除く)し、ブラウザに送信できるようにする
def messages_to_json(messages):
    to_dump = []
    for message in messages:
        if message['role'] != 'system':
            to_dump.append(message)
    return json.dumps(to_dump)


#OpenAIがまだ知らない情報を得るために呼び出せる関数のリスト(未使用)
def get_chatgpt_functions():
    return [
        {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["location"],
            },
        }
    ]


#この関数 execute_openai_function は、OpenAI APIからのレスポンスに含まれる関数呼び出し仕様（func_specification）を処理し、対応するローカルのPython関数を呼び出してその結果を返すためのもの
def execute_openai_function(func_specification) -> str:
    available_functions = {
        "get_current_weather": get_current_weather,
    }
    function_name = func_specification["name"]
    function_to_call = available_functions[function_name]       #呼び出し可能な関数の範囲を制限する（セキュリティ）
    function_args = json.loads(func_specification["arguments"])
    function_response = function_to_call(**function_args)
    return function_response


#同じ天気を返すようにハードコードされたダミー関数の例
#本番環境では、これはバックエンドAPIか外部APIになる
def get_current_weather(location, unit="fahrenheit"):
    return f"The weather in {location} is hot and sunny."

if __name__ == "__main__":
    app.run(debug=True)
