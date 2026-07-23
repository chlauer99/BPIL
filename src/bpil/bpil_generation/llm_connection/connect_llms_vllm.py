import asyncio
import requests
import re
import json
import time
from openai import OpenAI, AsyncOpenAI, timeout
from epmc_llm.llm_connection.connect_llms_ollama import ConnectLLMs

def vllm_is_geq_0120(base_url: str) -> tuple[str, bool]:
    def parse_version_tuple(vstr):
        m = re.match(r'^(\d+)\.(\d+)(?:\.(\d+))?', vstr or "")
        if not m:
            return None
        return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    try:
        resp = requests.get(f"{base_url}/version", timeout=5)
        resp.raise_for_status()
        vllm_ver_str = resp.json()["version"]
        if "dev" in vllm_ver_str:
            return vllm_ver_str, True
        parsed = parse_version_tuple(vllm_ver_str)
        if parsed is None:
            return vllm_ver_str, True
        return vllm_ver_str, parsed >= (0, 12, 0)
    except requests.RequestException as e:
        print(f"Warning: Could not detect vLLM version: {e}. Defaulting to structured_outputs.")
        return "", True
    except (KeyError, ValueError, TypeError) as e:
        print(f"Warning: Invalid version response format: {e}. Defaulting to structured_outputs.")
        return "", True

class ConnectLLMsVLLM(ConnectLLMs):
    """
    Class to connect to an LLM via VLLM API
    """

    def __init__(self, llm_modell, sys_msg, timeout=1800, grammar=None):
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
        print(self.llm, llm_modell)
        self.grammar = grammar

        #this is just for testing purposes to align with the example code
        self.base_url = "http://134.96.191.214:10112"
        #self.base_url = "http://134.96.191.214:10116"
        #client = OpenAI(base_url="http://134.96.191.214:10112/v1", api_key="EMPTY")
        self.async_client = AsyncOpenAI(base_url="http://134.96.191.214:10112/v1", api_key="EMPTY")
        #self.async_client = AsyncOpenAI(base_url="http://134.96.191.214:10116/v1", api_key="EMPTY")
        print(f"LLM {self.llm} is ready.")

        vllm_version, self.use_structured_outputs = vllm_is_geq_0120(self.base_url)
        grammar_format = "structured_outputs" if self.use_structured_outputs else "guided_grammar"
        print(f"vLLM {vllm_version} || grammar format: {grammar_format}")


        print(f"LLM {self.llm} is ready. The timeout is set to {timeout}")
        print("settings: ", "temp", self.temperature, "top k", self.top_k, "top p", self.top_p, "context length ", self.ctx_len, "think", self.think)

    async def call_api(self, id, messages, format):

        #elif "gpt" in self.llm:  # https://docs.unsloth.ai/basics/gpt-oss-how-to-run-and-fine-tune#recommended-settings
        #self.temperature = 1
        #self.top_k = 100
        #self.top_p = 1
        extra = {"top_k": self.top_k, "chat_template_kwargs": {"enable_thinking": True if self.think else False}}
        if self.grammar:
            if self.use_structured_outputs:
                extra["structured_outputs"] = {"grammar": self.grammar}
            else:
                extra["guided_grammar"] = self.grammar
        if format:
            response = await self.async_client.chat.completions.create(model=self.llm,
                                                                       messages=messages,
                                                                       temperature=self.temperature,
                                                                       stream=False,
                                                                       max_tokens=self.ctx_len,
                                                                       reasoning_effort= "low",
                                                                       #reasoning_effort="low",
                                                                       top_p=self.top_p,
                                                                       response_format=format,
                                                                       #extra_body={"top_k": self.top_k,"guided_json":format})
                                                                       extra_body=extra)
        else:
            if self.grammar:
                #streaming mode as workaround for lre_old dataset
                stream = await self.async_client.chat.completions.create(
                    model=self.llm,
                    messages=messages,
                    temperature=self.temperature,
                    stream=True,
                    max_tokens=self.ctx_len,
                    reasoning_effort="low",
                    extra_body=extra)
                response_content = ""
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        response_content += delta
                return (id, response_content)
            else:
                #streaming off for non-grammar calls
                response = await self.async_client.chat.completions.create(
                    model=self.llm,
                    messages=messages,
                    temperature=self.temperature,
                    stream=False,
                    max_tokens=self.ctx_len,
                    reasoning_effort="low",
                    extra_body=extra)
        """
        async for chunk in response:
            delta_content = chunk.choices[0].delta.content
            if delta_content in ["", None]:
                try:
                    delta_content = chunk.choices[0].delta.reasoning_content
                except AttributeError:
                    delta_content = None

            if delta_content:
                if first_token_time is None:
                    first_token_time = time.time()  # TTFT captured here
                # print(delta_content, end='', flush=True)
                eval_tokens += len(delta_content.split())  # approximate token count

            print(delta_content)

            return delta_content
        """
        return (id, response.choices[0].message.content)


    async def chat_without_history(self, request_list, format=None):
        tasks = [self.call_api(messages=request, id=id, format=format) for id, request in request_list]
        return await asyncio.gather(*tasks)
        """
        responses = []
        for id, request in request_list:
            start_time = time.perf_counter()
            tasks = [self.call_api(id, messages=request, format=format)]
            response = await asyncio.gather(*tasks)
            end_time = time.perf_counter()
            print(f"Time taken for request {id}: {end_time - start_time:} seconds")
            print("content")
            print(response)
            responses.extend(response)

        print("final response:")
        print(responses)
        return responses
        """

