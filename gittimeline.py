import os
from git import Repo
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px

# Function to find all Git repositories in given base directories
def find_git_repos(base_dirs):
    repos = []
    for base_dir in base_dirs:
        expanded_base_dir = os.path.expanduser(base_dir)
        for root, dirs, files in os.walk(expanded_base_dir):
            if '.git' in dirs:
                repo_name = os.path.basename(root)
                base_folder_name = os.path.basename(os.path.normpath(base_dir))
                repos.append((f"{base_folder_name}/{repo_name}", root, base_folder_name))
                dirs.remove('.git')  # Prevents searching inside .git directories
    return repos

# Base directories to search for Git repositories
base_dirs = ['~/Documents/GitLab', '~/Documents/GitHub']
repos = find_git_repos(base_dirs)

# List of branch names to check
branches = ['master', 'main']

commits = []
for repo_name, repo_path, base_folder in repos:
    repo = Repo(repo_path)
    for branch in branches:
        if branch in repo.heads:
            for commit in repo.iter_commits(branch):
                commit_time = datetime.fromtimestamp(commit.committed_date)
                if 5 <= commit_time.hour <= 22:  # Filter commits between 5 AM and 10 PM
                    commits.append({
                        'repo': repo_name,  # Use the full repo name with base folder
                        'branch': branch,
                        'hash': commit.hexsha,
                        'message': commit.message,
                        'date': commit_time,
                        'time': commit_time.strftime('%H:%M'),
                        'group': base_folder  # Add the base folder as group
                    })

# Convert commits list to DataFrame
df = pd.DataFrame(commits)

# Ensure the 'date' column is present and correctly formatted
if 'date' not in df.columns:
    raise KeyError("'date' column is missing from the DataFrame")

# Sort commits by date
df.sort_values(by='date', inplace=True)

# Set the range for the x-axis to the last 7 days
end_date = df['date'].max()
start_date = end_date - timedelta(days=7)

# Order the DataFrame by 'repo' alphabetically
df = df.sort_values(by='repo')

# Create the interactive timeline plot with different marker symbols for groups
accepted_symbols = ['circle', 'cross']
fig = px.scatter(df, x='date', y='time', color='repo', symbol='group', symbol_sequence=accepted_symbols, 
                 title='Commit History Timeline',
                 labels={'date': 'Date', 'time': 'Time of Day'},
                 hover_data={'hash': True, 'branch': True, 'message': True})

# Update layout for better readability and autosize
fig.update_layout(
    xaxis_title='Date',
    yaxis_title='Time of Day',
    xaxis_rangeslider_visible=True,
    autosize=True,
    xaxis=dict(range=[start_date, end_date])
)

# Remove text labels from the plot
fig.update_traces(marker=dict(size=10), selector=dict(mode='markers'))

# Save the plot to an HTML file
html_file_path = 'commit_history_timeline.html'
fig.write_html(html_file_path)

print(f"Timeline plot saved to {html_file_path}. Open this file in a web browser to view the interactive plot.")