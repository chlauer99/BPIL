import time

from ollama import Client
from copy import deepcopy
from pydantic import BaseModel

class ConnectLLMs():
    def __init__(self, llm_modell, sys_msg, timeout=300):
        self.llm = llm_modell
        self.chat_histroy = []
        self.sys_msg = sys_msg
        self.init_sys_role(sys_msg)

        self.ctx_len = 32768

        # --- Set some generation parameters ---
        # ollama defaults (https://github.com/ollama/ollama/blob/main/docs/modelfile.md#parameter):
        self.temperature = 0.8
        self.top_k = 40
        self.top_p = 0.9

        print(f"LLM {self.llm} is ready. The timeout is set to {timeout}")
        print("gpt" in self.llm, self.ctx_len, self.temperature, self.top_k, self.top_p)

        if "qwen2" in self.llm:
            print("qwen")
            self.temperature = 0.7
            self.top_k = 50
            self.top_p = 0.95
            self.ctx_len = 25000
        elif "qwen3" in self.llm:  # non-thinking values!
            print("qwen3")
            self.temperature = 0.7
            self.top_k = 20
            self.top_p = 0.8
        elif "llama3" in self.llm:
            print("llama3")
        elif "llama3" in self.llm or "Llama-3" in self.llm:
            self.temperature = 0.6
            self.top_p = 0.9
            self.ctx_len = 25000
        elif "gpt" in self.llm:  # https://docs.unsloth.ai/basics/gpt-oss-how-to-run-and-fine-tune#recommended-settings
            self.temperature = 1
            self.top_k = 100
            self.top_p = 1

        # --- Set thinking options ---
        if "gpt" in self.llm:
            self.think = "low"
            self.increased_think = "low"  # also low because in higher modes it generates too long thinking traces
        else:
            self.think = False
            self.increased_think = True if "qwen3:14b" in self.llm else False

        print("LLM:" in self.llm, "ctx: ", self.ctx_len, self.temperature, self.top_k, self.top_p, self.think)

    def init_sys_role(self, msg:str):
        """
        Allows to change the system message - history is deleted

        Parameters
        ----------
        msg: str
            new system message

       """
        self.chat_histroy = []
        self.chat_histroy.append({"role": "system", "content": msg})
        #self.chat_histroy.append({"role": "system", "content": [{"type": "text", "text": msg}]}) #mistral
        #self.chat_histroy.append({"role": "assistant", "content": response.message.content})

    def reset_chat_history(self):
        """
        deletes the chat history, without deleting the system message
        """
        if len(self.chat_histroy) > 1:
            self.chat_histroy = self.chat_histroy[:2]



class ConnectLLMsOllama(ConnectLLMs):
    """
    Class to connect to an LLM via Ollama API
    """
    def __init__(self, llm_modell, sys_msg, timeout=600):
        """
        Initalizes the class
        Parameters
        ----------
        llm_modell: str
            LLM model (ollama tag is neede)
        sys_msg: str
           System message
        timeout: int
            Timeout in seconds
        """
        super().__init__(llm_modell, sys_msg, timeout)
        self.client = Client(
            #host="http://192.168.92.194:10202", #server for research project
            host="http://134.96.191.214:10202",
            timeout=600
            #timeout=timeout
        )
        print(f"LLM {self.llm} is ready. The timeout is set to {timeout}")
        print(self.llm, self.chat_histroy)
        response = self.client.chat(model=self.llm, messages=self.chat_histroy)

    def chat_with_history(self, role:str, content:str, format=None):
        """
        Allows to send a request to the LLM and returns the response.
        The conversation is saved in the history

        Parameters
        ----------
        role: str
            Role of the request
        content: str
            Content of the request
        format: dict
            Desired format of the response - not mandatory

        Returns
        -------
        response: str
            Content string of response from the LLM
        """
        self.chat_histroy.append({"role": "user", "content": content})
        if format:
            response = self.client.chat(model=self.llm,
                                        messages=self.chat_histroy,
                                        format=format,
                                        think=self.think,
                                        options={"temperature": self.temperature,
                                                 "num_ctx": self.ctx_len,
                                                 "top_p": self.top_p,
                                                 "top_k": self.top_k})  # numctx = context
        else:
            response = self.client.chat(model=self.llm,
                                    messages=self.chat_histroy,
                                    think=self.think,
                                    options={"temperature": self.temperature,
                                             "num_ctx": self.ctx_len,
                                             "top_p": self.top_p,
                                             "top_k": self.top_k}) #numctx = context
        self.chat_histroy.append({"role": "assistant", "content": response.message.content})
        print(response)
        return response.message.content

    def chat_without_history(self, role:str, content:str, format=None):
        """
        Allows to send a request to the LLM and returns the response.
        The conversation is NOT saved in the history

        Parameters
        ----------
        role: str
            Role of the request
        content: str
            Content of the request
        format: dict
            Desired format of the response - not mandatory

        Returns
        -------
        response: dict
            Content string of response from the LLM
        """
        # history only consists of the system message
        msg = deepcopy(self.chat_histroy)
        msg.append({"role": role, "content": content})
        if format:
            response = self.client.chat(model=self.llm,
                                        messages=msg,
                                        format=format,
                                        think=self.think,
                                        options={"temperature": self.temperature,
                                                 "num_ctx": self.ctx_len,
                                                 "top_p": self.top_p,
                                                 "top_k": self.top_k})
        else:
            response = self.client.chat(model=self.llm,
                                        messages=msg,
                                        think=self.think,
                                        options={"temperature": self.temperature,
                                                 "num_ctx": self.ctx_len,
                                                 "top_p": self.top_p,
                                                 "top_k": self.top_k})
        print("Response", response)
        return response.message.content


