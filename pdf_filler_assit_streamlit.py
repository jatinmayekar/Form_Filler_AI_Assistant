import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime

import openai
import pandas as pd
import seaborn as sns
import streamlit as st
from fillpdf import fillpdfs
from load_dotenv import load_dotenv
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

# global values for pdf analysis
if 'st_page_number' not in st.session_state:
    st.session_state['st_page_number'] = -1

if 'st_input_pdf_path' not in st.session_state:
    st.session_state['st_input_pdf_path'] = ""

page_number = st.session_state['st_page_number']
input_pdf_path = st.session_state['st_input_pdf_path']
output_pdf_path = ""
fields = None
total_no_of_pages = -1


# Functions for the GPT assistant
class SuppressPrint:
    def __enter__(self):
        self._original_stdout = sys.stdout  # Backup original stdout
        sys.stdout = open(os.devnull, 'w')  # Redirect stdout to null device

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()  # Close the stream
        sys.stdout = self._original_stdout  # Restore original stdout


def get_current_page_number():
    global page_number
    page_number = st.session_state['st_page_number']
    return page_number


def set_current_page_number(input_page_number):
    global page_number
    page_number = st.session_state['st_page_number'] = input_page_number
    return page_number


def get_current_input_pdf_path():
    return input_pdf_path


def get_current_output_pdf_path():
    return output_pdf_path


def set_output_pdf_path():
    """
    Generate an output PDF path by appending the page number to the input PDF path before the file extension.
    :return: The path for the output PDF with the page number appended to the file name.
    """
    global output_pdf_path
    # Split the input path into directory, base name, and extension
    dir_name, base_name = os.path.split(input_pdf_path)
    name, ext = os.path.splitext(base_name)
    output_base_name = f"{name}_{page_number}{ext}"
    output_pdf_path = os.path.join(dir_name, output_base_name)
    return output_pdf_path


def get_current_fields():
    return fields


def get_current_total_number_of_pages():
    return total_no_of_pages


def store_input_pdf_path(pdf_path):
    global input_pdf_path
    global total_no_of_pages
    input_pdf_path = pdf_path
    st.session_state['st_input_pdf_path'] = pdf_path
    total_no_of_pages = get_pdf_len()
    return input_pdf_path


def get_pdf_len():
    return len(PdfReader(input_pdf_path).pages)


def get_latest_unfilled_page_number():
    global page_number
    global fields

    for i1 in range(total_no_of_pages):
        flag = False
        with SuppressPrint():
            fields = fillpdfs.get_form_fields(input_pdf_path, page_number=i1 + 1)
        for key, value2 in fields.items():
            if value2 != "":
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
        st.session_state['st_page_number'] = page_number
        return page_number


def get_fields_from_current_page():
    global fields
    fields = fillpdfs.get_form_fields(input_pdf_path=input_pdf_path, page_number=page_number)
    return fields


def set_fields():
    global output_pdf_path
    output_pdf_path = set_output_pdf_path()

    input_data_dict = get_dict_from_database_for_current_page()
    write_fillable_pdf_for_page_number(st.session_state['st_input_pdf_path'], output_pdf_path, input_data_dict,
                                       st.session_state['st_page_number'], flatten=True)
    return output_pdf_path


# Function to create the database and table
def create_database():
    conn = sqlite3.connect('key_value_store.db')
    cursor = conn.cursor()
    # Updated table schema to include 'page_number' column
    cursor.execute('''CREATE TABLE IF NOT EXISTS key_value_pairs (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        page_number INTEGER
                    )''')
    conn.commit()
    conn.close()


def check_table_exists():
    conn = sqlite3.connect('key_value_store.db')
    cursor = conn.cursor()
    # Query to check if the table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='key_value_pairs'")
    exists = cursor.fetchone()
    conn.close()
    return bool(exists)


def insert_key_value(key, value):
    # Check if the table exists, and if not, create the database and table
    if not check_table_exists():
        create_database()

    conn = sqlite3.connect('key_value_store.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO key_value_pairs (key, value, page_number) VALUES (?, ?, ?)",
                   (key, value, page_number))
    conn.commit()
    conn.close()


def update_key_value(key, new_value):
    conn = sqlite3.connect('key_value_store.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE key_value_pairs SET value = ? WHERE key = ? AND page_number = ?",
                   (new_value, key, page_number))
    conn.commit()
    conn.close()


def get_value_from_key(key):
    conn = sqlite3.connect('key_value_store.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM key_value_pairs WHERE key = ? AND page_number = ?",
                   (key, page_number))
    result = cursor.fetchone()
    conn.close()

    if result:
        return result[0]  # Return the value if the key exists in the database
    else:
        return None  # Return None if the key does not exist in the database


# Function to insert fields into database
def insert_dict_to_database(data):
    conn = sqlite3.connect('key_value_store.db')
    cursor = conn.cursor()
    for key, value in data.items():
        cursor.execute("INSERT OR REPLACE INTO key_value_pairs (key, value, page_number) VALUES (?, ?, ?)",
                       (key, value, page_number))
    conn.commit()
    conn.close()


def get_empty_fields_for_current_page():
    conn = sqlite3.connect('key_value_store.db')
    cursor = conn.cursor()

    page_number = get_current_page_number()

    # Retrieve empty fields for the specified page number
    cursor.execute("SELECT key FROM key_value_pairs WHERE page_number = ? AND value = ''", (page_number,))
    empty_fields = [row[0] for row in cursor.fetchall()]

    conn.close()

    return empty_fields


# Function to fetch key-value pairs from the database based on page number
def get_dict_from_database_for_current_page():
    conn = sqlite3.connect('key_value_store.db')
    cursor = conn.cursor()

    page_number = get_current_page_number()

    cursor.execute("SELECT key, value FROM key_value_pairs WHERE page_number = ?", (page_number,))
    rows = cursor.fetchall()
    conn.close()

    data_dict2 = {}
    for row in rows:
        key = row[0]
        value = row[1]
        data_dict2[key] = value

    return data_dict2


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

        Objective: "Must follow these steps to fill the pdf: 
        Initial Setup
        Initialize the Database
        
        Function: create_database
        This step prepares the storage for data that will be used in filling the PDF.
        Store the Input PDF Path
        
        Function: store_input_pdf_path
        Specify the path of the document to be processed.
        Process the Document
        Determine the Total Number of Pages
        
        Function: get_current_total_number_of_pages
        Knowing the total number of pages helps plan the filling process efficiently.
        Identify the Next Unfilled Page
        
        Function: get_latest_unfilled_page_number
        Focus efforts on pages that need attention by finding the next one with unfilled fields.
        Fill in the Fields
        Retrieve Fields for the Current Page
        
        Function: get_fields_from_current_page
        List all fields on the current page that need to be filled.
        Skip any field if its key is undefined
        Ask for User Input and Store Responses
        
        
        Step: For each field on the current page, prompt the user for input.
        Function: insert_key_value
        For every field, request the necessary data from the user. Store each piece of data in the database with the 
        appropriate key-value pair. This ensures that the field values are not only collected but also retained for any 
        necessary processing or reference.
        Update the Document
        Apply Data to the PDF
        
        Function: set_fields
        Fill the PDF fields based on the current page's data, utilizing the information stored in the database.
        Update the Output PDF Path
        
        Function: set_output_pdf_path
        Ensure the path of the updated document is correctly set, reflecting the changes made.
        Completion and Final Steps
        Repeat for Each Page
        
        Steps: Repeat the process of identifying unfilled pages, retrieving fields, asking for user input, storing 
        responses, and updating the PDF, for each page in the document until all fields are filled.
        Finalize the Filled PDF
        
        Function: get_current_output_pdf_path
        Ensure the filled PDF is correctly saved and provide the location of the filled document. This step marks the 
        completion of the filling process, ensuring that the document is ready for use.""",
        tools=[
            {"type": "code_interpreter"},
            {"type": "retrieval"},
            {
                "type": "function",
                "function": {
                    "name": "get_current_page_number",
                    "description": "Get the current page number.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_current_page_number",
                    "description": "Set the current page number. In cases, where the page returns no fields or no empty fields, use this to move to the next page number",
                    "parameters": {
                        "type": "object",  # Indicating the parameters should be structured as an object
                        "properties": {
                            "input_page_number": {
                                "type": "integer",
                                "description": "a page number"
                            }
                        },
                        "required": ["input_page_number"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_input_pdf_path",
                    "description": "Get the current input PDF path.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_output_pdf_path",
                    "description": "Get the current output PDF path.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_output_pdf_path",
                    "description": "Set the output PDF path based on the input PDF path and page number.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_fields",
                    "description": "Get the fields for the current page.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_total_number_of_pages",
                    "description": "Get the total number of pages in the PDF.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "store_input_pdf_path",
                    "description": "Store the input PDF path and calculate the total number of pages.",
                    "parameters": {
                        "type": "object",  # Indicating the parameters should be structured as an object
                        "properties": {
                            "pdf_path": {
                                "type": "string",
                                "description": "Path of the input pdf"
                            }
                        },
                        "required": ["pdf_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_pdf_len",
                    "description": "Get the length (number of pages) of the PDF.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_latest_unfilled_page_number",
                    "description": "Retrieve the latest unfilled page number.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_fields_from_current_page",
                    "description": "Retrieve fields from the current page.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_fields",
                    "description": "Set the fields in PDF based on current page's data retrieved from the database.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_database",
                    "description": "Create the SQLite database and table to store key-value pairs.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "insert_key_value",
                    "description": "Insert or update a key-value pair in the database.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "The key to insert/update."
                            },
                            "value": {
                                "type": "string",
                                "description": "The value associated with the key."
                            }
                        },
                        "required": ["key", "value"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_key_value",
                    "description": "Update the value of a key in the database.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "The key whose value needs to be updated."
                            },
                            "new_value": {
                                "type": "string",
                                "description": "The new value to set for the key."
                            }
                        },
                        "required": ["key", "new_value"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_value_from_key",
                    "description": "Retrieve the value associated with a key from the database.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "The key whose value needs to be retrieved."
                            }
                        },
                        "required": ["key"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "insert_dict_to_database",
                    "description": "Insert a dictionary into the database.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "object",
                                "description": "The dictionary to be inserted into the database.",
                                "additionalProperties": {
                                    "type": "string"
                                }
                            }
                        },
                        "required": ["data"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_empty_fields_for_current_page",
                    "description": "Retrieve empty fields for the current page.",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_dict_from_database_for_current_page",
                    "description": "Retrieve key-value pairs from the database for the current page.",
                    "parameters": {}
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

        # print("\nMessage: ", message)

        run_create = st.session_state.client.beta.threads.runs.create(
            thread_id=st.session_state.thread.id,
            assistant_id=st.session_state.assistant.id,
        )
        # print("\nRun create: ", run_create)

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
                    if tool_calls[i].function.name == "get_current_page_number":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Current page number: {get_current_page_number()}"
                        })
                    elif tool_calls[i].function.name == "set_current_page_number":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Set current page number as : {set_current_page_number(json.loads(tool_calls[i].function.arguments)['input_page_number'])}"
                        })
                    elif tool_calls[i].function.name == "get_current_input_pdf_path":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Current input PDF path: {get_current_input_pdf_path()}"
                        })
                    elif tool_calls[i].function.name == "get_current_output_pdf_path":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Current output PDF path: {get_current_output_pdf_path()}"
                        })
                    elif tool_calls[i].function.name == "set_output_pdf_path":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Output PDF path set to: {set_output_pdf_path()}"
                        })
                    elif tool_calls[i].function.name == "get_current_fields":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Current fields: {get_current_fields}"
                        })
                    elif tool_calls[i].function.name == "get_current_total_number_of_pages":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Total number of pages: {get_current_total_number_of_pages()}"
                        })
                    elif tool_calls[i].function.name == "store_input_pdf_path":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Input PDF path stored: "
                                      f"{store_input_pdf_path(json.loads(tool_calls[i].function.arguments)['pdf_path'])}"
                        })
                    elif tool_calls[i].function.name == "get_pdf_len":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Length of the PDF: {get_pdf_len()}"
                        })
                    elif tool_calls[i].function.name == "get_latest_unfilled_page_number":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Latest unfilled page number: {get_latest_unfilled_page_number()}"
                        })
                    elif tool_calls[i].function.name == "get_fields_from_current_page":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Fields from current page: {get_fields_from_current_page()}"
                        })
                    elif tool_calls[i].function.name == "set_fields":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Fields set, output path: {set_fields()}"
                        })
                    elif tool_calls[i].function.name == "create_database":
                        create_database()
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": "Database created successfully"
                        })
                    elif tool_calls[i].function.name == "insert_key_value":
                        arguments = json.loads(tool_calls[i].function.arguments)
                        insert_key_value(arguments['key'], arguments['value'])
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Key '{arguments['key']}' inserted with value '{arguments['value']}'"
                        })
                    elif tool_calls[i].function.name == "update_key_value":
                        arguments = json.loads(tool_calls[i].function.arguments)
                        update_key_value(arguments['key'], arguments['new_value'])
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Value for key '{arguments['key']}' updated to '{arguments['new_value']}'"
                        })
                    elif tool_calls[i].function.name == "insert_dict_to_database":
                        arguments = json.loads(tool_calls[i].function.arguments)
                        insert_dict_to_database(arguments['data'])
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": "Dictionary inserted into the database"
                        })
                    elif tool_calls[i].function.name == "get_value_from_key":
                        arguments = json.loads(tool_calls[i].function.arguments)
                        value = get_value_from_key(arguments['key'])
                        if value is not None:
                            msg.append({
                                "tool_call_id": tool_calls[i].id,
                                "output": f"Value for key '{arguments['key']}': {value}"
                            })
                        else:
                            msg.append({
                                "tool_call_id": tool_calls[i].id,
                                "output": f"Key '{arguments['key']}' not found in the database"
                            })
                    elif tool_calls[i].function.name == "get_empty_fields_for_current_page":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Empty fields for the current page: {get_empty_fields_for_current_page()}"
                        })
                    elif tool_calls[i].function.name == "get_dict_from_database_for_current_page":
                        msg.append({
                            "tool_call_id": tool_calls[i].id,
                            "output": f"Data from the database for the current page: "
                                      f"{get_dict_from_database_for_current_page()}"
                        })

                print("\nTool output: ", msg)

                run = st.session_state.client.beta.threads.runs.submit_tool_outputs(
                    thread_id=st.session_state.thread.id,
                    run_id=run.id,
                    tool_outputs=msg
                )
                # print("\nRun - Tool outputs: ", run)

        messages = st.session_state.client.beta.threads.messages.list(
            thread_id=st.session_state.thread.id
        )
        # print("\nMessages: ", messages)

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
