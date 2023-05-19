import requests
import sqlite3
import openai
import hashlib
from flask import Flask, render_template, request
from urllib.parse import quote

app = Flask(__name__)

conn = sqlite3.connect('kv_store.db')  # Connect to the SQLite database (it will be created if it doesn't exist)
cursor = conn.cursor()
# Create a table named kv_store with key and value columns if it does not exists yet...
cursor.execute('''
    CREATE TABLE IF NOT EXISTS kv_store(
        key TEXT UNIQUE,
        value TEXT
    );
''')
conn.commit()  # Commit the changes
conn.close()  # Close the connection


# A function to insert a key-value pair into the kv_store table...
def put_cache_value(key, value):
    # Connect to the SQLite database (it will be created if it doesn't exist)
    conn2 = sqlite3.connect('kv_store.db')
    cursor2 = conn2.cursor()
    try:
        cursor2.execute('''INSERT INTO kv_store(key, value) VALUES(?, ?)''', (key, value))
        conn2.commit()  # Commit the changes
        conn2.close()  # Close the connection
    except sqlite3.IntegrityError:
        print(f"Key {key} already exists.")


# A function to retrieve a value by key from the kv_store table
def get_cache_value(key):
    # Connect to the SQLite database (it will be created if it doesn't exist)
    conn2 = sqlite3.connect('kv_store.db')
    cursor2 = conn2.cursor()
    cursor2.execute('''SELECT value FROM kv_store WHERE key = ?''', (key,))
    result = cursor2.fetchone()
    conn2.close()  # Close the connection

    return result[0] if result else None


def hash_input(for_hash):
    # Create a SHA256 hash object
    sha256_hash = hashlib.sha256()

    # Update the hash object with the string to be hashed
    sha256_hash.update(for_hash.encode('utf-8'))

    return sha256_hash.hexdigest()  # Get the hexadecimal representation of the hashed value


openai.api_key = "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"  # os.environ.get("OPENAI_API_KEY")


def chat_gpt_cached_answer(chat_prompt):
    chat_gpt_model = "gpt-3.5-turbo"
    chat_prompt_hash = hash_input(chat_gpt_model + "|" + chat_prompt)
    print(f"Hash of {chat_gpt_model}|" + chat_prompt[0:30] + f"... je {chat_prompt_hash}")

    result = get_cache_value(chat_prompt_hash)
    if result is None:
        response = openai.ChatCompletion.create(
            model=chat_gpt_model,
            messages=[
                {"role": "user", "content": chat_prompt}
            ]
        )

        result = response['choices'][0]['message']['content']
        put_cache_value(chat_prompt_hash, result)
        return result
    else:
        return result


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/process_mr_url', methods=['POST'])
def process_mr_url():
    url = request.form['mr_url']

    result = process_url(url)  # Call your Python function here

    return render_template('index.html', result=result)


def process_url(url):
    # take URL and extract MR ID from it, then call GitLab API...

    gitlab_at = "glpat-aHvrnFvQUCbQym2_7ayM"  # os.environ.get("GITLAB_ACCESS_TOKEN")

    # Extract the project ID...
    project_id_start = url.find("gitlab.com/") + 11
    project_id_end = url.find("/-/", project_id_start)

    project_path_with_namespace = quote(url[project_id_start:project_id_end]).replace("/", "%2F")

    api_url_get_project_id = f"https://gitlab.com/api/v4/projects/{project_path_with_namespace}"
    print("API_URL_GetProjectID = " + api_url_get_project_id)

    # Send GET request to GitLab API
    headers = {"PRIVATE-TOKEN": gitlab_at}
    response = requests.get(api_url_get_project_id, headers=headers)

    # Check response status code
    if response.status_code == 200:
        # Parse response JSON to access project ID
        project_id = response.json()["id"]
        # print(f"Project ID: {projectID}")
    else:
        project_id = -1
        print(response.json())

    # Extract the string after the last slash
    last_slash_index = url.rfind("/")
    if last_slash_index != -1:
        merge_request_id = url[last_slash_index + 1:]
    else:
        merge_request_id = ""

    # GitLab API endpoint for retrieving merge request changes
    api_url_get_mrc_changes = f"https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{merge_request_id}/changes"
    # print("API_URL_GetMRCHanges = " + API_URL_GetMRCHanges)

    # Send GET request to GitLab API
    headers = {"PRIVATE-TOKEN": gitlab_at}
    response = requests.get(api_url_get_mrc_changes, headers=headers)

    mr_changes_str = ""
    changelog_str = ""

    # Check response status code
    if response.status_code == 200:
        # Parse response JSON to access changes data
        mr_changes = response.json()["changes"]

        # Process and display the changes
        for change in mr_changes:
            new_path = change["new_path"]
            old_path = change["old_path"]
            diff = change["diff"]
            # print(f"Diff for {new_path}:\n{diff}")
            diff_length = str(len(diff))

            if len(diff) > 3000:
                lines = diff.splitlines()
                filtered_lines = [line for line in lines if not line.startswith("-")]

                diff4cl = ""
                for line in filtered_lines:
                    line_without_minus = line[1:]
                    diff4cl = diff4cl + f"{line_without_minus}\n"

                cl4diff = diff4cl[0:3000]
            else:
                cl4diff = diff

            cl4diff_length = str(len(cl4diff))
            mr_changes_str = mr_changes_str + f">>>>>>>>>>    DIFFERENCES FOR {new_path} ({diff_length} / {cl4diff_length})     <<<<<<<<<<\n\n{cl4diff}\n\n\n"

            open_ai_promt = f"Propose a changelog entry in bullets for {cl4diff}"
            # open_ai_promt = f"Propose a descriptive changelog entry for {cl4diff}"

            cl4diff_result = chat_gpt_cached_answer(open_ai_promt)
            print("ChatGPT Response: " + cl4diff_result)

            changelog_str = changelog_str + f"Changes in {new_path}\n{cl4diff_result}\n\n"

        return url, mr_changes_str, project_path_with_namespace.replace("%2F", "/"), project_id, merge_request_id, changelog_str
    else:
        print(response.json())
        print(f"Failed to retrieve merge request changes. Status code: {response.status_code}")

        return url, mr_changes_str, project_path_with_namespace.replace("%2F", "/"), project_id, merge_request_id, changelog_str


if __name__ == '__main__':
    app.run(debug=True)
