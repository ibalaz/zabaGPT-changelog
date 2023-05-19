import os
import requests

from flask import Flask, render_template, request

app = Flask(__name__)

@app.route('/')

def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    url = request.form['mr_url']
    result = process_url(url)  # Call your Python function here

    return render_template('index.html', result=result)

def process_url(url):
    # take URL and extract MR ID from it, then call GitLab API...

    GitLab_AT = "glpat-aHvrnFvQUCbQym2_7ayM" #os.environ.get("GITLAB_ACCESS_TOKEN")
    
    # Extract the project ID...
    projectIDStart = url.find("gitlab.com/") + 11
    projectIDEnd = url.find("/-/", projectIDStart)

    from urllib.parse import quote
    projectPathWithNamespace = quote(url[projectIDStart:projectIDEnd]).replace("/", "%2F")

    API_URL_GetProjectID = f"https://gitlab.com/api/v4/projects/{projectPathWithNamespace}"
    print("API_URL_GetProjectID = " + API_URL_GetProjectID)

    # Send GET request to GitLab API
    headers = {"PRIVATE-TOKEN": GitLab_AT}
    response = requests.get(API_URL_GetProjectID, headers=headers)

    # Check response status code
    if response.status_code == 200:
        # Parse response JSON to access project ID
        projectID = response.json()["id"]
        #print(f"Project ID: {projectID}")
    else:
        projectID = -1
        print(response.json())
    
    # Extract the string after the last slash
    last_slash_index = url.rfind("/")
    if last_slash_index != -1:
        MergeRequestID = url[last_slash_index + 1:]
    else:
        MergeRequestID = ""

    # GitLab API endpoint for retrieving merge request changes
    API_URL_GetMRCHanges = f"https://gitlab.com/api/v4/projects/{projectID}/merge_requests/{MergeRequestID}/changes"
    #print("API_URL_GetMRCHanges = " + API_URL_GetMRCHanges)

    # Send GET request to GitLab API
    headers = {"PRIVATE-TOKEN": GitLab_AT}
    response = requests.get(API_URL_GetMRCHanges, headers=headers)

    MRChangesStr = ""
    Changelogstr = ""

    # Check response status code
    if response.status_code == 200:
        # Parse response JSON to access changes data
        MRChanges = response.json()["changes"]

        # Process and display the changes
        for change in MRChanges:
            new_path = change["new_path"]
            old_path = change["old_path"]
            diff = change["diff"]
            #print(f"Diff for {new_path}:\n{diff}")
            diffLength = str(len(diff))
            MRChangesStr = MRChangesStr + f">>>>>>>>>>    DIFFERENCES FOR {new_path} ({diffLength})     <<<<<<<<<<\n\n{diff}\n\n\n"

            if len(diff) > 3000:
                lines = diff.splitlines()
                filtered_lines = [line for line in lines if not line.startswith("-")]

                diff4cl = ""
                for line in filtered_lines:
                    diff4cl = diff4cl + f"{line}\n"

                cl4diff = diff4cl[0:3000]
            else:
                cl4diff = diff
            

            import openai

            openai.api_key = "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" #os.environ.get("OPENAI_API_KEY")

            openAIPromt = f"Propose a descriptive changelog entry for: {cl4diff}"
            print(openAIPromt)
            
            """
            response = openai.ChatCompletion.create(
                engine='text-davinci-003',
                prompt=openAIPromt,
                max_tokens=2000,
                n=1,
                stop=None,
                temperature=0.6,
                frequency_penalty=0.0,
                presence_penalty=0.0
            )
            cl4diffResult = response.choices[0].text
            """

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": openAIPromt}
                ]
            )
            cl4diffResult = response['choices'][0]['message']['content']

            print("ChatGPT Response: " + str(response))

            diffLength = str(len(cl4diff))
            Changelogstr = Changelogstr + f">>>>>>>>>>    Changelog.md for {new_path} ({diffLength})     <<<<<<<<<<\n\n{cl4diffResult}\n\n\n"

        return url, MRChangesStr, projectPathWithNamespace.replace("%2F", "/"), projectID, MergeRequestID, Changelogstr
    else:
        print(response.json())
        print(f"Failed to retrieve merge request changes. Status code: {response.status_code}")

        return url, MRChangesStr, projectPathWithNamespace.replace("%2F", "/"), projectID, MergeRequestID, Changelogstr
    

if __name__ == '__main__':
    app.run()
