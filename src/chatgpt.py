import json
from collections import OrderedDict

import logging
from openai import OpenAI

from .crawler import WebCrawler


class Cache(OrderedDict):
    def __init__(self, max_capacity):
        super().__init__()
        self.max_capacity = max_capacity

    def __setitem__(self, key, value):
        if key in self:
            del self[key]
        elif len(self) == self.max_capacity:
            self.popitem(last=False)
        OrderedDict.__setitem__(self, key, value)

    def __getitem__(self, key):
        if key in self:
            value = OrderedDict.__getitem__(self, key)
            del self[key]
            OrderedDict.__setitem__(self, key, value)
            return value
        else:
            raise KeyError(key)


class ChatGPTDone(Exception):
    pass


def register_tool(description, params):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            return func(self, *args, **kwargs)

        # Set metadata without causing recursion
        wrapper.is_tool = True
        wrapper.tool_metadata = {
            "name": func.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {param['name']: {k: v for k, v in param.items() if k != 'name' and k != 'required'} for
                               param in params},
                "required": [param['name'] for param in params if param.get('required', False)]
            }
        }
        return wrapper

    return decorator


class ChatGPTCrawler():
    def __init__(
            self,
            debug=False,
            verbose=False,
            model="gpt-4-1106-preview",
            web_cache_size=16,
    ) -> None:
        super().__init__()
        self.model = model
        self.debug = debug
        self.verbose = verbose or debug

        self.messages = []
        self.completions = []
        self.contacts = []
        self.visited_url = None

        self._observers = []
        self._state = None

        self.webcrawler = WebCrawler(
            headless=not self.debug
        )
        self.api = OpenAI()

        self.web_cache = Cache(max_capacity=web_cache_size)

        self.start_url = None
        self.total_tokens_used = 0
        self.input_tokens_used = 0
        self.output_tokens_used = 0

    @property
    def tools(self):
        tool_methods = []
        for attr_name in dir(self):
            # Skip the 'tools' property and other special methods or properties
            if attr_name in ['tools', '__class__', '__module__', '__doc__'] or attr_name.startswith('__'):
                continue

            attr = getattr(self, attr_name)
            if callable(attr) and getattr(attr, 'is_tool', False):
                tool_methods.append({
                    "type": "function",
                    "function": attr.tool_metadata
                })
        return tool_methods

    def start(self, prompt_templates, **prompt_kwargs):
        self.start_url = prompt_kwargs.get('url', None)
        # Start prompt
        start_prompt = prompt_templates.format(**prompt_kwargs)
        self.messages.append(
            {
                "role": "user",
                "content": start_prompt
            }
        )
        while True:
            try:
                self._step()
            except ChatGPTDone:
                break
        # return contacts
        return self.contacts

    def reset(self):
        self.messages = []
        self.completions = []
        self.contacts = []
        self.start_url = None
        self.total_tokens_used = 0
        self.input_tokens_used = 0
        self.output_tokens_used = 0
        # TODO: craweler reset?

    """
    Private methods
    """

    def _step(self):
        comp = self._chat_gpt_api_request()
        comp = comp.choices[0]
        message = comp.message
        if message is None:
            if self.verbose:
                logging.info("ChatGPT didn't return a message")
            raise ChatGPTDone

        # check if function call
        if self._handle_function_call(message):
            # return so in the next step chat gpt can handle the function calls
            return

        # if we are not in debug, stop here
        if not self.debug:
            raise ChatGPTDone

        # is a regular chat message
        logging.info(f"ChatGPT:\n{message.content}")
        logging.info('')
        user_input = input("You ('q' to stop): ")
        if user_input == 'q':
            raise ChatGPTDone
        self.messages.append(
            {
                "role": "user",
                "content": user_input
            }
        )

    def _handle_function_call(self, message):
        if message.tool_calls is None:
            return False

        # append all tool call results to the messages
        for tool_call in message.tool_calls:
            tool = tool_call.function
            args = json.loads(tool.arguments)

            output = getattr(self, tool.name)(**args)

            self.messages.append(
                {
                    "role": "function",
                    "content": output,
                    "name": tool.name,
                }
            )

        return True

    def _chat_gpt_api_request(self, prompt=None):
        if prompt is not None:
            self.messages += [{"role": "user", "content": prompt}]
        completion = self.api.chat.completions.create(
          model=self.model,
          messages=self.messages,
          tools=self.tools,
          tool_choice="auto",
          seed=42,
          temperature=0.0, # make it deterministic
          #top_p=0.00001, # make it (more) deterministic
        )

        self.total_tokens_used += completion.usage.total_tokens
        self.input_tokens_used += completion.usage.prompt_tokens
        self.output_tokens_used += completion.usage.completion_tokens
        self.completions.append(completion)
        
        return completion

    """
    TOOLS for ChatGPT
    """

    @register_tool(
        description="Visit a URL and return the HTML",
        params=[
            {"name": "url", "type": "string", "description": "The URL to visit (can be absolute or relative)",
             "required": True}
        ]
    )
    def visit_url(self, url):
        if url in self.web_cache:
            if self.verbose:
                print(f"Using cached version of url {url}")
            return self.web_cache[url]
        if self.verbose:
            self.visited_url = url
        self.change_state(url)
        self.webcrawler.load_url(url)
        clean_html = self.webcrawler.get_cleaned_html()
        self.web_cache[url] = clean_html
        return clean_html

    @register_tool(
        description="Save a contact",
        params=[
            {"name": "name", "type": "string", "description": "The name of the contact", "required": True},
            {"name": "political_party", "type": "string", "description": "The political party of the contact",
             "required": False},
            {"name": "position", "type": "string", "description": "The position of the contact, i.e. 'Vorsitzender' ",
             "required": False},
            {"name": "email", "type": "string", "description": "The email of the contact", "required": False},
            {"name": "phone", "type": "string", "description": "The phone number of the contact", "required": False},
            {"name": "contact_url", "type": "string", "description": "The url of the contact", "required": False},
            {"name": "address", "type": "string", "description": "The address of the contact", "required": False},
            {"name": "additional_info", "type": "string", "description": "Additional information about the contact", "required": False},
        ]
    )
    def save_contact(
        self,
        name,
        political_party=None,
        position=None,
        email=None,
        phone=None,
        contact_url=None,
        address=None,
        additional_info=None,
    ):
        # turn to json
        contact = {
            "name": name,
            "political_party": political_party,
            "position": position,
            "email": email,
            "phone": phone,
            "contact_url": contact_url,
            "address": address,
            "additional_info": additional_info,
            "start_url": self.start_url, # url where the search started
        }

        self.contacts.append(contact)
        msg = f"Successfully saved contact: {contact}"
        if self.verbose:
            logging.info(msg)
        return msg

    """
    ConcreteSubject Methods
    """

    def attach(self, observer):
        self._observers.append(observer)

    def detach(self, observer):
        self._observers.remove(observer)

    def notify(self):
        for observer in self._observers:
            observer(self._state)

    def change_state(self, new_state):
        self._state = new_state
        self.notify()
