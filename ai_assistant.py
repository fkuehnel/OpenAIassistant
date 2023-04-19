import http.client
import json
import re
import sublime
import sublime_plugin
from concurrent.futures import ThreadPoolExecutor

def plugin_loaded() -> None:
    pass

class OpenAIRequest():
    def __init__(self, token: str, api_endpoint: str):
        self.api_endpoint = api_endpoint
        self.header = {
            "Authorization": "Bearer {}".format(token),
            "Content-Type": "application/json",
            "cache-control": "no-cache",
        }

    def run(self, payload):
        conn = http.client.HTTPSConnection("api.openai.com")
        try:
            conn.request("POST", self.api_endpoint, json.dumps(payload), self.header)
            resp = conn.getresponse()
            response_json  = json.loads(resp.read().decode('utf-8'))

            if 'text' in response_json['choices'][0]:
                return response_json['choices'][0]['text']
            elif 'message' in response_json['choices'][0]:
                return response_json['choices'][0]['message']['content']
            else:
                raise KeyError()
        except KeyError:
            sublime.error_message("Response Error:\n{}".format(response_json))
        except Exception as ex:
            sublime.error_message("Server Error {}: {}\n{}".format(
                str(resp.status), ex, response_json)
            )
        finally:
            conn.close()

class TaskHelper():
    def __init__(self, task_name, action_name):
        settings = sublime.load_settings("OpenAIassist.sublime-settings")
        self.token = settings.get('token')
        self.task = settings.get("tasks").get(task_name)
        self.api_endpoint = self.task.get('api_endpoint')
        actions = self.task.get('actions') or {}
        self.action = actions.get(action_name) or {}
        if len(self.action) == 0:
            sublime.error_message("Invalid task action:\n{}".format(action_name))

    def get_token(self) -> str:
        return self.token or 'not_defined'

    def get_api_endpoint(self) -> str:
        return self.api_endpoint or "/v1/completions"

    def show_command(self) -> str:
        return self.action.get('show') or 'new_tab'

    def get_payload(self, text: str):
        if self.action is not None:
            prompt = self.action.get('prompt') or ''
            payload = {
                "model": self.task.get("model"),
                "n": 1,
                "temperature": self.task.get("temperature") or 0.9,
            }
            if self.api_endpoint == '/v1/edits':
                payload['instruction'] = prompt
                payload['input'] = text
                return payload

            payload['max_tokens'] = self.task.get("max_tokens") or 1024
            payload['stop'] = None
            if self.api_endpoint == '/v1/chat/completions':
                payload['messages'] = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}]
            else:
                payload['prompt'] = "{} which follows here: \"{}\"".format(
                    prompt, text)

            return payload

    def display_result(self, edit, view, region, new_text) -> None:
        command = self.action.get('show') or 'new_tab'
        if command == 'replace':
            view.replace(edit, region, new_text)
            view.add_regions('AI generated', [region],
                'region.purplish', 'dot', sublime.PERSISTENT)
        elif command == 'add':
            num_char = view.insert(edit, region.end(), new_text)
            new_region = sublime.Region(region.end(), region.end() + num_char)
            view.add_regions('AI generated', [new_region],
                'region.purplish', 'dot', sublime.PERSISTENT)
        else:
            new_tab = view.window().new_file().set_name('AI generated')
            new_tab.insert(edit, 0, new_text)

class AiTextAssistCommand(sublime_plugin.TextCommand):
    def is_enabled(self):
        return True  # always true, maybe change that?

    def run(self, edit, task, action):
        for region in self.view.sel():
            if not region.empty():
                task_helper = TaskHelper(task, action)
                sel_text = self.view.substr(region)
 
                request = OpenAIRequest(task_helper.get_token(), task_helper.get_api_endpoint())
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(request.run, task_helper.get_payload(sel_text))

                ai_text = future.result()
                task_helper.display_result(edit, self.view, region, ai_text)

class AiCodeAssistCommand(sublime_plugin.TextCommand):
    def is_enabled(self):
        name = self.view.file_name()
        res = re.match(".+\\.(html|js|py|go|cc|c|swift)$", name)
        return res is not None

    def run(self, edit, task, action):
        for region in self.view.sel():
            if not region.empty():
                task_helper = TaskHelper(task, action)
                sel_text = self.view.substr(region)

                request = OpenAIRequest(task_helper.get_token(), task_helper.get_api_endpoint())
                with ThreadPoolExecutor() as executor:
                    future = executor.submit(request.run, task_helper.get_payload(sel_text))

                ai_text = future.result()
                task_helper.display_result(edit, self.view, region, ai_text)