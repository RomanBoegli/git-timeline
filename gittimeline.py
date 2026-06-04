import os
import json
import argparse
import html
from git import Repo
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import re
import webbrowser

ALL_BRANCHES = "_all_"

def load_config(config_file_path):
    with open(config_file_path) as config_file:
        return json.load(config_file)

def normalize_branches(branches):
    if isinstance(branches, str):
        return [branches]
    return branches

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

def resolve_branches(repo, branches):
    if ALL_BRANCHES in branches:
        return sorted(head.name for head in repo.heads)

    resolved_branches = []
    for branch in branches:
        if branch in repo.heads and branch not in resolved_branches:
            resolved_branches.append(branch)
    return resolved_branches

def has_pending_changes(repo, branches):
    """Check if a repo has uncommitted changes or unpushed commits."""
    # Check for uncommitted changes (staged, unstaged, or untracked)
    if repo.is_dirty(untracked_files=True):
        return True
    # Check for unpushed commits on any of the tracked branches
    for branch in branches:
        if branch in repo.heads:
            local_branch = repo.heads[branch]
            tracking = local_branch.tracking_branch()
            if tracking is not None:
                try:
                    ahead = list(repo.iter_commits(f'{tracking.name}..{local_branch.name}'))
                    if ahead:
                        return True
                except Exception:
                    pass
    return False

def collect_commits(repos, branches, committers_patterns, time_back_scope, start_hour, end_hour):
    commits = []
    seen_commits = {}
    for repo_name, repo_path, base_folder in repos:
        repo = Repo(repo_path)
        repo_branches = resolve_branches(repo, branches)
        pending = has_pending_changes(repo, repo_branches)
        display_name = f"* {os.path.basename(repo.working_tree_dir)}" if pending else os.path.basename(repo.working_tree_dir)
        for branch in repo_branches:
            branch_commits = process_branch(
                repo,
                branch,
                committers_patterns,
                time_back_scope,
                start_hour,
                end_hour,
                base_folder,
                display_name,
            )
            for commit in branch_commits:
                key = (repo_path, commit["hash"])
                if key in seen_commits:
                    existing_branches = seen_commits[key]["branch"].split(", ")
                    if branch not in existing_branches:
                        seen_commits[key]["branch"] = f'{seen_commits[key]["branch"]}, {branch}'
                    continue

                seen_commits[key] = commit
                commits.append(commit)
    return commits

def process_branch(repo, branch, committers_patterns, time_back_scope, start_hour, end_hour, base_folder, display_name=None):
    branch_commits = []
    since = time_back_scope.strftime("%Y-%m-%d %H:%M:%S")
    for commit in repo.iter_commits(branch, since=since):
        commit_time = datetime.fromtimestamp(commit.committed_date)
        if commit_time >= time_back_scope and start_hour <= commit_time.hour <= end_hour:
            if is_valid_committer(commit.committer.email, committers_patterns):
                branch_commits.append(process_commit(commit, repo, branch, base_folder, display_name))
    return branch_commits

def is_valid_committer(email, committers_patterns):
    return any(pattern.match(email) for pattern in committers_patterns)

def process_commit(commit, repo, branch, base_folder, display_name=None):
    diff = commit.stats.total['lines']
    size_category = categorize_commit_size(diff)
    return {
        'repo': display_name if display_name else os.path.basename(repo.working_tree_dir),
        'committer': commit.committer.email,
        'branch': branch,
        'hash': commit.hexsha,
        'message': commit.message,
        'date': datetime.fromtimestamp(commit.committed_date),
        'time': datetime.fromtimestamp(commit.committed_date).strftime('%H:%M'),
        'group': base_folder,
        'change_lines': diff,
        'change_size_cat': size_category
    }

def categorize_commit_size(diff):
    if diff < 20:
        return 'small'
    elif diff < 100:
        return 'normal'
    else:
        return 'big'

def create_commit_dataframe(commits):
    df = pd.DataFrame(commits)
    if df.empty:
        raise KeyError("No relevant commits found")
    if 'date' not in df.columns:
        raise KeyError("'date' column is missing from the DataFrame")
    df.sort_values(by='date', inplace=True)
    return df

def format_hover_text(value, max_length=None):
    text = " ".join(str(value).split())
    if max_length is not None and len(text) > max_length:
        text = f"{text[:max_length - 3].rstrip()}..."
    return html.escape(text)

def format_committer(email):
    if "@" not in email:
        return format_hover_text(email, 48)

    name, domain = email.split("@", 1)
    if domain == "users.noreply.github.com":
        email = name
    return format_hover_text(email, 56)

def split_branch_names(branches):
    return [branch.strip() for branch in branches.split(",") if branch.strip()]

def add_repo_legend_labels(df):
    branches_by_repo = {}
    for repo, repo_branches in df.groupby('repo')['branch']:
        branches = sorted({
            branch
            for branch_list in repo_branches
            for branch in split_branch_names(branch_list)
        })
        branches_by_repo[repo] = f"{repo} ({', '.join(branches)})"

    df['repo_label'] = df['repo'].map(branches_by_repo)
    return df

def generate_plot(df, start_hour, end_hour):
    end_date = df['date'].max() + timedelta(days=1)
    start_date = end_date - timedelta(days=8)

    tick_start = datetime(2000, 1, 1, start_hour)
    tick_end = datetime(2000, 1, 1, end_hour) + timedelta(hours=1)
    hourly_ticks = pd.date_range(tick_start, tick_end, freq="h").strftime('%H:%M')
    all_possible_ticks = pd.date_range(tick_start, tick_end, freq="1min").strftime('%H:%M')

    df = df.copy()
    df['time'] = pd.Categorical(df['time'], categories=all_possible_ticks, ordered=True)

    df = df.sort_values(by=['group', 'repo'])
    df = add_repo_legend_labels(df)

    size_map = {'small': 1, 'normal': 2, 'big': 4}
    df['change_size_num'] = df['change_size_cat'].map(size_map)
    df['short_hash'] = df['hash'].str[:8]
    df['repo_hover'] = df['repo'].map(format_hover_text)
    df['branch_hover'] = df['branch'].map(format_hover_text)
    df['committer_hover'] = df['committer'].map(format_committer)
    df['message_hover'] = df['message'].map(lambda message: format_hover_text(message, 110))

    accepted_symbols = ['circle', 'square', 'diamond', 'cross', 'x', 'triangle-up']
    color_sequence = (
        px.colors.qualitative.Bold
        + px.colors.qualitative.Dark24
        + px.colors.qualitative.Alphabet
    )
    fig = px.scatter(
        df,
        x='date',
        y='time',
        color='repo_label',
        symbol='group',
        symbol_sequence=accepted_symbols,
        color_discrete_sequence=color_sequence,
        size='change_size_num',
        size_max=18,
        title='Commit History Timeline',
        labels={'date': 'Date', 'time': 'Time of Day'},
        custom_data=[
            'repo_hover',
            'branch_hover',
            'short_hash',
            'committer_hover',
            'message_hover',
            'change_lines',
            'change_size_cat',
        ],
    )

    fig.update_layout(
        xaxis_title='Date',
        yaxis_title='Time of Day',
        xaxis_rangeslider_visible=True,
        autosize=True,
        margin=dict(l=72, r=28, t=72, b=58),
        plot_bgcolor='white',
        paper_bgcolor='white',
        hovermode='closest',
        hoverlabel=dict(
            bgcolor='rgba(255, 255, 255, 0.98)',
            bordercolor='#4b5563',
            align='left',
            font=dict(
                color='#111827',
                size=13,
                family='Arial, sans-serif',
            ),
        ),
        legend=dict(
            title_text='Repository',
            orientation='v',
            itemsizing='constant',
            font=dict(size=12),
        ),
        xaxis=dict(
            range=[start_date, end_date],
            tickformat="%b %d (%a)\n%Y",
            gridcolor='#eaeef2',
            zeroline=False,
            rangeslider=dict(
                bgcolor='rgba(241, 245, 249, 0.55)',
                bordercolor='#cbd5e1',
                borderwidth=1,
                thickness=0.08,
            ),
        ),
        yaxis=dict(
            categoryorder='array',
            categoryarray=all_possible_ticks,
            tickvals=hourly_ticks,
            gridcolor='#f1f3f5',
        ),
    )

    fig.update_traces(
        selector=dict(mode='markers'),
        marker=dict(line=dict(width=1.25, color='black'), opacity=0.68),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Branch: %{customdata[1]}<br>"
            "Commit: %{customdata[2]}<br>"
            "Committer: %{customdata[3]}<br>"
            "When: %{x|%b %d, %Y} at %{y}<br>"
            "Change: %{customdata[5]} lines (%{customdata[6]})<br>"
            "<br>%{customdata[4]}"
            "<extra></extra>"
        ),
    )

    return fig

def save_and_open_plot(fig, html_file_path, browser):
    fig.write_html(
        html_file_path,
        config={'responsive': True},
        default_width='100%',
        default_height='100vh',
    )
    print(f"Timeline plot saved to {html_file_path}. Open this file in a web browser to view the interactive plot.")
    browser_path = webbrowser.get(browser)
    browser_path.open('file:///' + os.path.abspath(html_file_path))

def parse_args():
    parser = argparse.ArgumentParser(description="Visualize commits from multiple git repositories.")
    parser.add_argument("--config", default="config.json", help="Path to the JSON config file.")
    return parser.parse_args()

def get_work_hours(config):
    start_hour = config.get("start_hour", 5)
    end_hour = config.get("end_hour", 22)
    if not isinstance(start_hour, int) or not isinstance(end_hour, int):
        raise ValueError("start_hour and end_hour must be integers.")
    if start_hour < 0 or end_hour > 23 or start_hour > end_hour:
        raise ValueError("start_hour and end_hour must define a valid hour range between 0 and 23.")
    return start_hour, end_hour

def main():
    args = parse_args()
    config = load_config(args.config)
    base_dirs = config['base_dirs']
    branches = normalize_branches(config['branches'])
    committers_patterns = [re.compile(pattern) for pattern in config['committers']]
    days = config['days']
    browser = config['browser']
    start_hour, end_hour = get_work_hours(config)

    repos = find_git_repos(base_dirs)
    time_back_scope = datetime.now() - timedelta(days=days)
    commits = collect_commits(repos, branches, committers_patterns, time_back_scope, start_hour, end_hour)
    df = create_commit_dataframe(commits)
    print(df)
    fig = generate_plot(df, start_hour, end_hour)
    save_and_open_plot(fig, 'commit_history_timeline.html', browser)

if __name__ == "__main__":
    main()
