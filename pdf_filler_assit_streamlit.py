# import os
# import sys
import json
# import datetime
# import random
# import re
import logging
import os
import sys
# import requests
import time
from datetime import datetime

import matplotlib.pyplot as plt
import openai
import pandas as pd
import seaborn as sns
# import tiktoken
import streamlit as st
from fillpdf import fillpdfs
# from pathlib import Path
# import tkinter as tk
# import base64
# from io import StringIO
# from tkinter import messagebox
# import sqlite3
from load_dotenv import load_dotenv
# import pandas as pd
# import numpy as np
# import matplotlib.pyplot as plt
# import pyaudio
# import wave
# import cv2
from openai import OpenAI
from pdfrw import PdfReader

from pdf_fill_write import write_fillable_pdf_for_page_number

load_dotenv()

# Initialize logging
logging.basicConfig(filename='chatgpt_analyzer.log', level=logging.INFO)

# Suppress info logging from OpenAI API only warnings and errors will still be logged
logging.getLogger('openai._base_client').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

ai_model = "gpt-4-1106-preview"
user_id = 46
user_query = ""
ai_response = ""
thread_id = 0
turn_count = 0
start_time = datetime.now()
end_time = datetime.now()
conversation_history = ""
analyzer_response_value_display = ""
# encoding = tiktoken.get_encoding("cl100k_base")
user_token = 0
ai_token = 0
total_tokens = 0
imageFlag = False
use_camera_flag = False
prompt = ""
createImageFlag = False
image_url = ""


# Functions for the GPT assistant
class SuppressPrint:
    def __enter__(self):
        self._original_stdout = sys.stdout  # Backup original stdout
        sys.stdout = open(os.devnull, 'w')  # Redirect stdout to null device

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()  # Close the stream
        sys.stdout = self._original_stdout  # Restore original stdout


def get_total_no_of_pages(input_pdf_path):
    return len(PdfReader(input_pdf_path).pages)


def get_latest_unfilled_page_with_fields(input_pdf_path):
    page_number = -1
    total_no_of_pages = get_total_no_of_pages(input_pdf_path)
    # print("Total no of pages: ", total_no_of_pages)

    for i1 in range(total_no_of_pages):
        flag = False
        with SuppressPrint():
            fields = fillpdfs.get_form_fields(input_pdf_path, page_number=i1 + 1)
        for key, value in fields.items():
            if value != "":
                # page is filled, so skip and go to next page
                flag = True
                break
        if not flag:
            # unfilled page found
            page_number = i1 + 1
            break

    if page_number == -1:
        return None
    else:
        return page_number, fields


def set_fields(input_pdf_path, output_pdf_path, data_dict, page_number):
    write_fillable_pdf_for_page_number(input_pdf_path, output_pdf_path, data_dict, page_number, flatten=True)
    return output_pdf_path


# Streamlit app
# Initialize session state if not already done
if 'timestamps' not in st.session_state:
    st.session_state['timestamps'] = []

openai.api_key = os.getenv("OPEN_API_KEY")
if 'client' not in st.session_state:
    st.session_state.client = OpenAI()

st.title("PDF filler GPT")

with st.sidebar:
    st.title("Upload files here")
    uploaded_file = st.file_uploader("Choose a file")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Upload a file with an "assistants" purpose
# file_og = st.session_state.client.files.create(
#   file=open("link.txt", "rb"),
#   purpose='assistants'
# )

if 'assistant' not in st.session_state:
    st.session_state.assistant = st.session_state.client.beta.assistants.create(
        name="PDF Filler Assistant",
        model="gpt-4-1106-preview",
        instructions="""Context: "Assist users in filling out a PDF form by guiding them through each step, utilizing 
        predefined functions to streamline the process, and providing clarifications for any uncertainties within the 
        document. If the user expresses uncertainty about any text within the PDF, offer explanations or definitions 
        to clarify. This may involve simple restatements in layman's terms or providing context to ensure 
        understanding. Leverage external knowledge where necessary to provide accurate and comprehensive 
        explanations, while ensuring the information shared respects privacy and security standards."
                
        Additional resource: "Reach out to parth.thakkar@yourcfp.com for any queries or assistance."

        Style: "Simple, structured, clean, and clear"
        
        Tone: "Maintain a friendly and professional tone throughout the interaction, ensuring the user feels 
        supported and understood. ust use first person style - as you are the world's best assistant dedicated to 
        help user fill the pdf"

        Objective: "Must follow these steps to fill the pdf: 1. Greet the users and ask for the local full path to 
        the pdf file 2. Get the latest unfilled page number and its fillable fields in a dictionary format using 
        find_latest_unfilled_page_with_fields function. The dictionary is named as data_dict and is defined as 
        data_dict = {'field1': 'value1', 'field2': 'value2', ...}, where each field is a key and the value is the 
        user's response to the fillable field 3. Use the key values of the dictionary to create prompts to ask the 
        user to fill in the blanks and then store the user's response in the values of that dictionary against the 
        corresponding key. Complete the data_dict with the user's responses. Must ensure the format of the dictionary 
        is correct. example: data_dict = {'Name': 'Jon', 'Date of Birth': '03/05/2001', 'Address': '44 Melrone Stree, 
        Manhattan, NY-4906', 'Mobile': '2974505939', ...} 4. Send this completed data_dict dictionary to the 
        set_fields function to fill the pdf with users answers. For the output_pdf_path, use the same path as the 
        input_pdf_path with the suffix '_Complete' with the current page number added to the file name 5. Provide the 
        output_pdf_path to the user 6. Repeat steps 2-5 until all the pages are filled 7. Thank the user for using 
        the service and offer further assistance or direct them to additional resources if needed""",
        tools=[
            {"type": "code_interpreter"},
            {"type": "retrieval"},
            {"type": "function",
             "function":
                 {
                     "name": "get_latest_unfilled_page_with_fields",
                     "description": "Get the latest unfilled page number & its fillable fields in a dictionary format",
                     "parameters":
                         {
                             "type": "object",
                             "properties":
                                 {
                                     "input_pdf_path":
                                         {
                                             "type": "string",
                                             "description": "The local full path to the pdf file"
                                         }
                                 },
                             "required":
                                 [
                                    "input_pdf_path"
                                 ]
                         }
                 }
             },
            {"type": "function",
             "function":
                 {
                     "name": "set_fields",
                     "description": "Set the fillable fields in the pdf with the user's responses",
                     "parameters":
                         {
                             "type": "object",
                             "properties":
                                 {
                                     "input_pdf_path":
                                         {
                                             "type": "string",
                                             "description": "The local full path to the pdf file"
                                         },
                                     "output_pdf_path":
                                         {
                                             "type": "string",
                                             "description": "The local full path to the output pdf file"
                                         },
                                     "data_dict":
                                         {
                                             "type": "object",
                                             "description": "The data_dict dictionary containing the user's responses "
                                                            "to the fillable fields"
                                         },
                                     "page_number":
                                         {
                                             "type": "integer",
                                             "description": "The page number to fill"
                                         }
                                 },
                             "required":
                                 [
                                     "input_pdf_path",
                                     "output_pdf_path",
                                     "data_dict",
                                     "page_number"
                                 ]
                         }
                 }
             }
        ]
        # file_ids=[file_og.id]
    )

    # assistant_file_1 = st.session_state.client.beta.assistants.files.create(
    #     assistant_id=st.session_state.assistant.id,
    #     file_id=file_og.id
    # )

    print("\nAssistant: ", st.session_state.assistant)

if 'thread' not in st.session_state:
    st.session_state.thread = st.session_state.client.beta.threads.create()
    print("Thread: ", st.session_state.thread)

if "prev_uploaded_file" not in st.session_state:
    st.session_state.prev_uploaded_file = None

prompt = st.chat_input("Ask here...")
if prompt is None:
    prompt = ""
print("\nPrompt: ", prompt)

if prompt != "":
    start_time = datetime.now()

    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.status("Thinking...", expanded=False) as status:
        if uploaded_file is not None:
            # To read file as bytes:
            bytes_data = uploaded_file.getvalue()

            file_name = uploaded_file.name
            print(file_name)
            print(st.session_state.prev_uploaded_file)

            if st.session_state.prev_uploaded_file is not file_name:
                print("\nFile changed")
                with open(file_name, 'wb') as f:
                    f.write(bytes_data)
                st.success("PDF file saved successfully.")

                file_1 = st.session_state.client.files.create(
                    file=open(file_name, "rb"),
                    purpose='assistants'
                )

                st.session_state.prev_uploaded_file = file_name

                message = st.session_state.client.beta.threads.messages.create(
                    thread_id=st.session_state.thread.id,
                    role="user",
                    content=prompt,
                    file_ids=[file_1.id]
                )
            else:
                print("\nFile not changed")
                message = st.session_state.client.beta.threads.messages.create(
                    thread_id=st.session_state.thread.id,
                    role="user",
                    content=prompt
                )
        elif uploaded_file is None:
            print("\nNo file uploaded")
            message = st.session_state.client.beta.threads.messages.create(
                thread_id=st.session_state.thread.id,
                role="user",
                content=prompt
            )

        print("\nMessage: ", message)

        run_create = st.session_state.client.beta.threads.runs.create(
            thread_id=st.session_state.thread.id,
            assistant_id=st.session_state.assistant.id,
        )
        print("\nRun create: ", run_create)

        while True:
            time.sleep(1)
            run = st.session_state.client.beta.threads.runs.retrieve(
                thread_id=st.session_state.thread.id,
                run_id=run_create.id
            )
            status.update(label=run.status, state="running", expanded=False)
            if run.status == "completed":
                status.update(label=run.status, state="complete", expanded=False)
                break
            if run.status == "requires_action":
                msg = []
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                print("\nTool calls: ", tool_calls)

                for i in range(len(tool_calls)):
                    if tool_calls[i].function.name == "get_latest_unfilled_page_with_fields":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": json.dumps(get_latest_unfilled_page_with_fields(
                                input_pdf_path=json.loads(tool_calls[i].function.arguments)['input_pdf_path']))
                        })
                    elif tool_calls[i].function.name == "set_fields":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": set_fields(
                                input_pdf_path=json.loads(tool_calls[i].function.arguments)['input_pdf_path'],
                                output_pdf_path=json.loads(tool_calls[i].function.arguments)['output_pdf_path'],
                                data_dict=json.loads(tool_calls[i].function.arguments)['data_dict'],
                                page_number=json.loads(tool_calls[i].function.arguments)['page_number'])
                        })

                print("\nTool output: ", msg)

                run = st.session_state.client.beta.threads.runs.submit_tool_outputs(
                    thread_id=st.session_state.thread.id,
                    run_id=run.id,
                    tool_outputs=msg
                )
                print("\nRun - Tool outputs: ", run)

        messages = st.session_state.client.beta.threads.messages.list(
            thread_id=st.session_state.thread.id
        )
        print("\nMessages: ", messages)

    print("\nResponse", messages.data[0].content[0].text.value)
    response = messages.data[0].content[0].text.value

    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.markdown(response)

    input_audio_flag = False
    end_time = datetime.now()
    user_query = prompt
    ai_response = response
    thread_id = st.session_state.thread.id
    turn_count = len(st.session_state.messages)
    start_time = start_time
    end_time = end_time
    conversation_history = json.dumps(st.session_state.messages)

with st.sidebar:
    st.write("User ID ", user_id)
    st.write("Model: gpt-4-1106-preview")
    st.write("Timestamp ", start_time)

    current_time = pd.Timestamp.now()  # or use any other method to get the current time
    st.session_state['timestamps'].append(current_time)

    # Convert to DataFrame
    df = pd.DataFrame({'Timestamp': st.session_state['timestamps']})

    # Plotting (if there are timestamps)
    if not df.empty:
        # Extracting hour of the day for daily analysis
        df['Hour'] = df['Timestamp'].dt.hour

        # Plotting Hourly Distribution
        plt.figure(figsize=(10, 4))
        sns.histplot(df['Hour'], bins=24, kde=False)
        plt.title('Hourly Interaction Frequency')
        plt.xlabel('Hour of the Day')
        plt.ylabel('Number of Interactions')
        plt.xticks(range(0, 24))
        plt.grid(True)

        # Display the plot in Streamlit
        st.pyplot(plt)

    response_time_seconds = (end_time - start_time).total_seconds()

    st.write("Thread ID: ", thread_id)
    st.write("Count: ", turn_count)
    st.write("Response Time (seconds): ", str(response_time_seconds))
