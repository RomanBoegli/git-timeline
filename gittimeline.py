import os
from git import Repo
from datetime import datetime
import pandas as pd
import plotly.express as px

# Function to find all Git repositories in given base directories
def find_git_repos(base_dirs):
    repos = []
    for base_dir in base_dirs:
        expanded_base_dir = os.path.expanduser(base_dir)
        for root, dirs, files in os.walk(expanded_base_dir):
            if '.git' in dirs:
                repos.append(root)
                dirs.remove('.git')  # Prevents searching inside .git directories
    return repos

# Base directories to search for Git repositories
base_dirs = ['~/Documents/GitLab', '~/Documents/GitHub']
repos = find_git_repos(base_dirs)

# List of branch names to check
branches = ['master', 'main']

commits = []

for repo_path in repos:
    repo = Repo(repo_path)
    for branch in branches:
        if branch in repo.heads:
            for commit in repo.iter_commits(branch):
                commits.append({
                    'repo': os.path.basename(repo_path),  # Get the repo name from the path
                    'branch': branch,
                    'hash': commit.hexsha,
                    'message': commit.message,
                    'date': datetime.fromtimestamp(commit.committed_date)
                })

# Check the collected commits data
print("Collected commits data:")
for commit in commits:
    print(commit)

# Convert commits list to DataFrame
df = pd.DataFrame(commits)

# Check the DataFrame structure
print("DataFrame structure:")
print(df.head())

# Ensure the 'date' column is present and correctly formatted
if 'date' not in df.columns:
    raise KeyError("'date' column is missing from the DataFrame")

# Sort commits by date
df.sort_values(by='date', inplace=True)

# Create the interactive timeline plot
fig = px.scatter(df, x='date', y='repo', text='message',
                 title='Commit History Timeline',
                 labels={'date': 'Date', 'repo': 'Repository'},
                 hover_data={'hash': True, 'branch': True})

# Update layout for better readability
fig.update_layout(
    xaxis_title='Date',
    yaxis_title='Repository',
    xaxis_rangeslider_visible=True,
    height=600
)

fig.update_traces(marker=dict(size=10), selector=dict(mode='markers+text'))

# Save the plot to an HTML file
html_file_path = 'commit_history_timeline.html'
fig.write_html(html_file_path)

print(f"Timeline plot saved to {html_file_path}. Open this file in a web browser to view the interactive plot.")
