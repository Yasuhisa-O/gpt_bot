import os
import json
import openai
import mistune
from flask import Flask, flash, render_template, request

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
app.secret_key = 'chatbot-session-key'              # change this to be unique for your application


@app.route("/", methods=("GET", "POST"))
def index():
    if request.method == "POST":
        conversation_so_far = request.form.get('conversation_so_far', None)
        user_message = request.form.get('user_message', '')
        model = request.form.get('model', 'gpt-4')
        key = request.form.get('key', os.getenv("OPENAI_API_KEY"))
        openai.api_key = key
        messages = [{"role": "system", "content": render_template('system_prompt.txt')}]

        # rebuild messages list based on the contents of the hidden field used to store the conversation history
        if conversation_so_far and conversation_so_far != '':
            messages += parse_conversation(conversation_so_far)
        # append last user message to the messages list
        if user_message != '':
            messages.append({"role": "user", "content": user_message})

        # call the OpenAI API
        error_occurred = False
        try:
            response = openai.ChatCompletion.create(
                model=model,             # change to gpt-3.5-turbo once function calling is included. As of 23 June, only 0613 has it.
                messages=messages,
                #functions=get_chatgpt_functions(),
                temperature=0.7,
            )
        except openai.error.RateLimitError as e:    # OpenAI is too busy
            flash('Sorry, the server is overloaded right now. Please try again later.', 'error')
            error_occurred = True
        except openai.error.TryAgain as e:
            flash('Sorry, the server is overloaded right now. Please try again later.', 'error')
            error_occurred = True
        except openai.error.ServiceUnavailableError as e:
            flash('Sorry, the server is overloaded right now. Please try again later.', 'error')
            error_occurred = True
        except Exception as e:
            flash('Sorry, something went wrong. Please try again later', 'error')
            error_occurred = True

        if not error_occurred:
            # if OpenAI needs us to get some data for it the response contains a 'function_call' structure.
            if response.choices[0]['message'].get('function_call'):
                messages.append({"role": "function", "name": response.choices[0]['message'].get('function_call')['name'],
                                 "content": execute_openai_function(response.choices[0]['message'].get('function_call'))
                                 })
            else:   # otherwise, append the result from the API call to the messages
                messages.append({"role": "assistant", "content": response.choices[0]['message']['content'].strip()})

        return render_template("index.html", conversation=messages_to_html(messages),
                               conversation_json=messages_to_json(messages))

    return render_template("index.html")


@app.route('/settings', methods=('GET', 'POST'))
def settings():
    return render_template('settings.html')


def parse_conversation(conversation_so_far):
    return json.loads(conversation_so_far)


# format the messages list as HTMl, excluding the system prompt
def messages_to_html(messages):
    html = ''
    for message in messages:
        if message['role'] != 'system':
            message_content = mistune.html(message['content'])
            html += render_template('message.html', role=message['role'], content=message_content)
    return html


# turn the messages into JSON (excluding the system prompt) so they can be sent to the browser
def messages_to_json(messages):
    to_dump = []
    for message in messages:
        if message['role'] != 'system':
            to_dump.append(message)
    return json.dumps(to_dump)


# a list of functions that OpenAI can call to get information that it doesn't know yet
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


# execute a local Python function and pass it the arguments provided by OpenAI
def execute_openai_function(func_specification) -> str:
    available_functions = {
        "get_current_weather": get_current_weather,
    }
    function_name = func_specification["name"]
    function_to_call = available_functions[function_name]       # limit the range of possible functions that can be called (security)
    function_args = json.loads(func_specification["arguments"])
    function_response = function_to_call(**function_args)
    return function_response


# Example dummy function hard coded to return the same weather
# In production, this could be your backend API or an external API
def get_current_weather(location, unit="fahrenheit"):
    return f"The weather in {location} is hot and sunny."

if __name__ == "__main__":
    app.run(debug=True)
