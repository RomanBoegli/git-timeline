import os
import json
from git import Repo
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import re
import webbrowser

# Load configuration from JSON file
with open('config.json') as config_file:
    config = json.load(config_file)

# Extract variables from configuration
base_dirs = config['base_dirs']
branches = config['branches']
committers_patterns = [re.compile(pattern) for pattern in config['committers']]
days = config['days']
browser = config['browser']

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

repos = find_git_repos(base_dirs)
time_back_scope = datetime.now() - timedelta(days=days)

commits = []
for repo_name, repo_path, base_folder in repos:
    repo = Repo(repo_path)
    for branch in branches:
        if branch in repo.heads:
            for commit in repo.iter_commits(branch):
                commit_time = datetime.fromtimestamp(commit.committed_date)
                committer_email = commit.committer.email
                if commit_time >= time_back_scope and 5 <= commit_time.hour <= 22:
                    if any(pattern.match(committer_email) for pattern in committers_patterns):
                        diff = commit.stats.total['lines']
                        if diff < 20:
                            size_category = 'small'
                        elif diff < 100:
                            size_category = 'normal'
                        else:
                            size_category = 'big'
                        commits.append({
                            'repo': os.path.basename(repo_path),  # Use the full repo name with base folder
                            'committer': committer_email,
                            'branch': branch,
                            'hash': commit.hexsha,
                            'message': commit.message,
                            'date': commit_time,
                            'time': commit_time.strftime('%H:%M'),
                            'group': base_folder,  # Add the base folder as group
                            'change_lines': diff,
                            'change_size_cat': size_category
                        })

# Convert commits list to DataFrame
df = pd.DataFrame(commits)

# Some checks
if df.__len__ == 0:
    raise KeyError("no relevant commits found")
if 'date' not in df.columns:
    raise KeyError("'date' column is missing from the DataFrame")

# Sort commits by date
df.sort_values(by='date', inplace=True)

# Set the range for the x-axis to the last 7 days
end_date = df['date'].max() + timedelta(days=1)
start_date = end_date - timedelta(days=8)

# Generate hourly time labels between 05:00 and 22:00
hourly_ticks = pd.date_range("05:00", "20:00", freq="h").strftime('%H:%M')
all_possible_ticks = pd.date_range("05:00", "20:00", freq="1min").strftime('%H:%M')

# Ensure all possible time ticks are included in the 'time' column
df['time'] = pd.Categorical(df['time'], categories=all_possible_ticks, ordered=True)

# Order the DataFrame by 'repo' alphabetically
df = df.sort_values(by=['group', 'repo'])

# Map change_size to numerical values for marker sizes
size_map = {'small': 1, 'normal': 2, 'big': 4}
df['change_size_num'] = df['change_size_cat'].map(size_map)

# Create the interactive timeline plot with different marker symbols for groups
accepted_symbols = ['circle', 'cross']
fig = px.scatter(df, x='date', y='time', color='repo', symbol='group', symbol_sequence=accepted_symbols, size='change_size_num',
                 title='Commit History Timeline',
                 labels={'date': 'Date', 'time': 'Time of Day'},
                 hover_data={'hash': True, 'committer': True,'branch': True, 'message': True, 'change_lines': True, 'change_size_cat': True})

# Update layout for better readability and autosize
fig.update_layout(
    xaxis_title='Date',
    yaxis_title='Time of Day',
    xaxis_rangeslider_visible=True,
    autosize=True,
    xaxis=dict(
        range=[start_date, end_date],
        tickformat="%b %d (%a)\n%Y"
    ),
    yaxis=dict(categoryorder='array', categoryarray=all_possible_ticks, tickvals=hourly_ticks)
)

# Remove text labels from the plot
fig.update_traces(selector=dict(mode='markers'))

# Save the plot to an HTML file
html_file_path = 'commit_history_timeline.html'
fig.write_html(html_file_path)

print(f"Timeline plot saved to {html_file_path}. Open this file in a web browser to view the interactive plot.")

# Open the HTML file in the specified browser
browser_path = webbrowser.get(browser)
browser_path.open('file:///' + os.path.abspath(html_file_path))
